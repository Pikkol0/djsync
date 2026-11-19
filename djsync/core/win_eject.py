"""1.4.3 (A7-4) : éjection d'une clé sous Windows comme « Retirer le périphérique en toute sécurité ».

Repris de Sleeve (https://github.com/alii/sleeve, GPL-2.0-or-later, crates/rbl-devices/src/eject.rs et
eject/windows.rs). Constat de Sleeve : verrouiller le volume (FSCTL_LOCK_VOLUME) échoue (« Accès refusé »,
erreur 5) dès qu'un programme, même l'Explorateur ou l'indexation, tient un fichier ouvert sur la clé. La demande
Plug and Play (CM_Request_Device_EjectW) demande au contraire à chaque programme de lâcher la clé, vide et démonte
le système de fichiers, et refuse (« veto ») tant que quelque chose reste ouvert : une clé occupée n'est jamais
forcée. Le volume n'est interrogé que sans droit de lecture ni d'écriture (pas besoin d'administrateur).

La partie Windows (ctypes) n'est appelée que sous Windows ; le choix du périphérique à éjecter (`eject_target`)
et les messages sont purs et testés partout.
"""
from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator, List, Optional, Tuple, TypeVar

log = logging.getLogger(__name__)

N = TypeVar("N")
ATTEMPTS = 3                 # une demande refusée est répétée : l'Explorateur met un instant à lâcher la clé
RETRY_DELAY_S = 0.5

DEVICE, MEDIA, REFUSE = "device", "media", "refuse"

# PNP_VETO_TYPE (cfg.h)
VETO_UNKNOWN, VETO_PENDING_CLOSE, VETO_WINDOWS_APP, VETO_WINDOWS_SERVICE = 0, 2, 3, 4
VETO_OUTSTANDING_OPEN, VETO_INSUFFICIENT_RIGHTS, VETO_ALREADY_REMOVED = 5, 12, 13


class EjectError(OSError):
    """Éjection refusée ; `reason` : "in_use", "in_use_by", "rights", "gone", "not_removable", "failed"."""

    def __init__(self, reason: str, name: str = "") -> None:
        super().__init__(f"{reason}{': ' + name if name else ''}")
        self.reason, self.name = reason, name


@dataclass(frozen=True)
class DeviceNode:
    removable: bool = False      # CM_DEVCAP_REMOVABLE : ce qui met un périphérique dans « Retirer en toute sécurité »
    interface: bool = False      # interface USB d'un périphérique composite (USB\VID_…&PID_…&MI_nn\…)
    hub: bool = False            # concentrateur USB : l'éjecter couperait tout ce qui y est branché


def drive_letter(path: str) -> Optional[str]:
    """Lettre d'une racine de lecteur (« E:\\ » → « E »), None pour tout autre chemin."""
    text = str(path)
    if len(text) == 3 and text[0].isalpha() and text[1] == ":" and text[2] in "\\/":
        return text[0].upper()
    return None


def multi_strings(buffer: Iterable[str]) -> Iterator[str]:
    """Chaînes d'une liste Windows (REG_MULTI_SZ) : chacune finit par un NUL, une chaîne vide finit la liste."""
    text = "".join(buffer)
    for item in text.split("\0"):
        if not item:
            return
        yield item


def is_interface_id(instance_id: str) -> bool:
    parts = instance_id.split("\\")
    return len(parts) >= 2 and parts[0].upper() == "USB" and "&MI_" in parts[1].upper()


def is_hub(instance_id: str, compatible_ids: Iterable[str], service: str) -> bool:
    up = instance_id.upper()
    return (up.startswith("USB\\ROOT_HUB") or any(c.upper().startswith("USB\\CLASS_09") for c in compatible_ids)
            or service.lower() in ("usbhub", "usbhub3"))


def eject_target(disk: N, removable_media: bool, parent: Callable[[N], Optional[N]],
                 describe: Callable[[N], DeviceNode]) -> Tuple[str, Optional[N]]:
    """Ce qu'il faut éjecter pour `disk`, comme « Retirer en toute sécurité » : son parent s'il est amovible (clé) ;
    à travers un seul nœud « interface » (lecteurs de cartes composites) ; jamais un concentrateur ; sinon le
    disque lui-même ; sinon le support (carte d'un lecteur intégré) ; sinon refus (disque interne)."""
    def ejectable(node: DeviceNode) -> bool:
        return node.removable and not node.hub

    up = parent(disk)
    if up is not None:
        first = describe(up)
        if ejectable(first):
            return DEVICE, up
        if first.interface and not first.hub:
            device = parent(up)
            if device is not None and ejectable(describe(device)):
                return DEVICE, device
    if ejectable(describe(disk)):
        return DEVICE, disk
    if removable_media:
        return MEDIA, None
    return REFUSE, None


def veto_reason(veto_type: int, name: str) -> EjectError:
    """Raison d'un refus de Windows ; le programme est nommé quand Windows le donne (« explorer.exe »)."""
    short = (name or "").strip().replace("/", "\\").split("\\")[-1].strip()
    if veto_type in (VETO_WINDOWS_APP, VETO_WINDOWS_SERVICE) and short:
        return EjectError("in_use_by", short)
    if veto_type in (VETO_WINDOWS_APP, VETO_WINDOWS_SERVICE, VETO_OUTSTANDING_OPEN, VETO_PENDING_CLOSE):
        return EjectError("in_use")
    if veto_type == VETO_INSUFFICIENT_RIGHTS:
        return EjectError("rights")
    if veto_type == VETO_ALREADY_REMOVED:
        return EjectError("gone")
    return EjectError("failed")


# ----------------------------------------------------------------------------------------- Windows
def eject(root: str) -> None:
    """Éjecte la clé de la racine `root` (« E:\\ »). Lève EjectError (refus expliqué) ou OSError."""
    if sys.platform != "win32":                                    # pragma: no cover - Windows seulement
        raise EjectError("failed", "not Windows")
    letter = drive_letter(root)
    if letter is None:
        raise EjectError("failed", "not a drive root")
    return _Win().eject(letter)


class _Win:                                                         # pragma: no cover - Windows seulement
    CR_SUCCESS, CR_BUFFER_SMALL = 0, 0x1A
    CM_DRP_COMPATIBLEIDS, CM_DRP_SERVICE, CM_DRP_CAPABILITIES = 0x03, 0x05, 0x10
    CM_DEVCAP_REMOVABLE = 0x04
    CM_GET_DEVICE_INTERFACE_LIST_PRESENT = 0
    FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING = 1, 2, 3
    GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
    IOCTL_STORAGE_GET_DEVICE_NUMBER = 0x2D1080
    FSCTL_LOCK_VOLUME, FSCTL_DISMOUNT_VOLUME, IOCTL_STORAGE_EJECT_MEDIA = 0x90018, 0x90020, 0x2D4808
    FILE_DEVICE_DISK, DRIVE_REMOVABLE, ERROR_ACCESS_DENIED = 7, 2, 5

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes as W

        self.c, self.W = ctypes, W
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.cfg = ctypes.WinDLL("cfgmgr32")

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", W.DWORD), ("Data2", W.WORD), ("Data3", W.WORD), ("Data4", ctypes.c_ubyte * 8)]

        class DEVPROPKEY(ctypes.Structure):
            _fields_ = [("fmtid", GUID), ("pid", W.ULONG)]

        class SDN(ctypes.Structure):
            _fields_ = [("DeviceType", W.DWORD), ("DeviceNumber", W.ULONG), ("PartitionNumber", W.ULONG)]

        self.SDN = SDN
        # GUID_DEVINTERFACE_DISK {53f56307-b6bf-11d0-94f2-00a0c91efb8b}
        self.disk_guid = GUID(0x53F56307, 0xB6BF, 0x11D0, (ctypes.c_ubyte * 8)(0x94, 0xF2, 0x00, 0xA0, 0xC9, 0x1E,
                                                                                 0xFB, 0x8B))
        # DEVPKEY_Device_InstanceId {78c34fc8-104a-4aca-9ea4-524d52996e57}, 256
        self.instance_key = DEVPROPKEY(GUID(0x78C34FC8, 0x104A, 0x4ACA, (ctypes.c_ubyte * 8)(
            0x9E, 0xA4, 0x52, 0x4D, 0x52, 0x99, 0x6E, 0x57)), 256)
        self.k32.CreateFileW.restype = W.HANDLE
        self.k32.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
        self.k32.DeviceIoControl.argtypes = [W.HANDLE, W.DWORD, ctypes.c_void_p, W.DWORD, ctypes.c_void_p, W.DWORD,
                                             ctypes.POINTER(W.DWORD), ctypes.c_void_p]
        self.k32.CloseHandle.argtypes = [W.HANDLE]
        self.invalid = W.HANDLE(-1).value

    # ---------------------------------------------------------------- volume et disque
    def _open(self, path: str, access: int = 0) -> int:
        h = self.k32.CreateFileW(path, access, self.FILE_SHARE_READ | self.FILE_SHARE_WRITE, None,
                                 self.OPEN_EXISTING, 0, None)
        if h == self.invalid or h is None:
            raise self.c.WinError(self.c.get_last_error())
        return h

    def _ioctl(self, h: int, code: int, out: object = None, size: int = 0) -> None:
        ret = self.W.DWORD(0)
        ptr = self.c.byref(out) if out is not None else None
        if not self.k32.DeviceIoControl(h, code, None, 0, ptr, size, self.c.byref(ret), None):
            raise self.c.WinError(self.c.get_last_error())

    def device_number(self, path: str) -> Tuple[int, int]:
        h = self._open(path)
        try:
            n = self.SDN()
            self._ioctl(h, self.IOCTL_STORAGE_GET_DEVICE_NUMBER, n, self.c.sizeof(n))
            return int(n.DeviceType), int(n.DeviceNumber)
        finally:
            self.k32.CloseHandle(h)

    def disk_interfaces(self) -> List[str]:
        c, W = self.c, self.W
        for _ in range(ATTEMPTS):
            length = W.ULONG(0)
            code = self.cfg.CM_Get_Device_Interface_List_SizeW(c.byref(length), c.byref(self.disk_guid), None,
                                                               self.CM_GET_DEVICE_INTERFACE_LIST_PRESENT)
            if code != self.CR_SUCCESS:
                raise EjectError("failed", f"list disks {code}")
            buf = c.create_unicode_buffer(length.value or 1)
            code = self.cfg.CM_Get_Device_Interface_ListW(c.byref(self.disk_guid), None, buf, length,
                                                          self.CM_GET_DEVICE_INTERFACE_LIST_PRESENT)
            if code == self.CR_SUCCESS:
                return list(multi_strings(buf[:length.value]))
            if code != self.CR_BUFFER_SMALL:
                raise EjectError("failed", f"list disks {code}")
        raise EjectError("failed", "list disks")

    def instance_id(self, interface: str) -> str:
        c, W = self.c, self.W
        buf = c.create_unicode_buffer(256)
        kind, size = W.ULONG(0), W.ULONG(512)
        code = self.cfg.CM_Get_Device_Interface_PropertyW(interface, c.byref(self.instance_key), c.byref(kind),
                                                          buf, c.byref(size), 0)
        if code != self.CR_SUCCESS:
            raise EjectError("failed", f"disk id {code}")
        return buf.value

    def disk_node(self, number: int) -> int:
        c, W = self.c, self.W
        for iface in self.disk_interfaces():
            try:
                kind, n = self.device_number(iface)
            except OSError:
                continue
            if kind != self.FILE_DEVICE_DISK or n != number:
                continue
            node = W.DWORD(0)
            code = self.cfg.CM_Locate_DevNodeW(c.byref(node), self.instance_id(iface), 0)
            if code != self.CR_SUCCESS:
                raise EjectError("failed", f"locate disk {code}")
            return int(node.value)
        raise EjectError("gone")

    # ---------------------------------------------------------------- arbre Plug and Play
    def parent(self, node: int) -> Optional[int]:
        up = self.W.DWORD(0)
        return int(up.value) if self.cfg.CM_Get_Parent(self.c.byref(up), node, 0) == self.CR_SUCCESS else None

    def device_id(self, node: int) -> str:
        buf = self.c.create_unicode_buffer(256)
        return buf.value if self.cfg.CM_Get_Device_IDW(node, buf, 255, 0) == self.CR_SUCCESS else ""

    def registry(self, node: int, prop: int) -> List[str]:
        c, W = self.c, self.W
        size = W.ULONG(0)
        if self.cfg.CM_Get_DevNode_Registry_PropertyW(node, prop, None, None, c.byref(size), 0) != self.CR_BUFFER_SMALL:
            return []
        buf = c.create_unicode_buffer(size.value // 2 + 2)
        size = W.ULONG((size.value // 2 + 1) * 2)
        if self.cfg.CM_Get_DevNode_Registry_PropertyW(node, prop, None, buf, c.byref(size), 0) != self.CR_SUCCESS:
            return []
        return list(multi_strings(buf[:len(buf)]))

    def removable(self, node: int) -> bool:
        c, W = self.c, self.W
        caps, size = W.DWORD(0), W.ULONG(4)
        code = self.cfg.CM_Get_DevNode_Registry_PropertyW(node, self.CM_DRP_CAPABILITIES, None, c.byref(caps),
                                                          c.byref(size), 0)
        return code == self.CR_SUCCESS and bool(caps.value & self.CM_DEVCAP_REMOVABLE)

    def describe(self, node: int) -> DeviceNode:
        ident = self.device_id(node)
        service = (self.registry(node, self.CM_DRP_SERVICE) or [""])[0]
        return DeviceNode(self.removable(node), is_interface_id(ident),
                          is_hub(ident, self.registry(node, self.CM_DRP_COMPATIBLEIDS), service))

    # ---------------------------------------------------------------- éjection
    def request_eject(self, node: int) -> None:
        c, W = self.c, self.W
        last = EjectError("failed")
        for attempt in range(ATTEMPTS):
            if attempt:
                time.sleep(RETRY_DELAY_S)
            veto = c.c_int(VETO_UNKNOWN)
            name = c.create_unicode_buffer(260)                    # nom fourni : pas de bulle de Windows
            code = self.cfg.CM_Request_Device_EjectW(node, c.byref(veto), name, 260, 0)
            if code == self.CR_SUCCESS and veto.value == VETO_UNKNOWN:
                return
            log.info("Windows vetoed the USB eject (attempt %d, code %s, veto %s, %s)", attempt + 1, code,
                     veto.value, name.value)
            last = veto_reason(veto.value, name.value)
        raise last

    def eject_media(self, volume: str) -> None:
        try:
            h = self._open(volume, self.GENERIC_READ | self.GENERIC_WRITE)
        except OSError as exc:
            if getattr(exc, "winerror", None) == self.ERROR_ACCESS_DENIED:
                raise EjectError("rights") from exc
            raise
        try:
            for attempt in range(ATTEMPTS):
                try:
                    self._ioctl(h, self.FSCTL_LOCK_VOLUME)
                    break
                except OSError as exc:
                    if getattr(exc, "winerror", None) != self.ERROR_ACCESS_DENIED:
                        raise
                    if attempt == ATTEMPTS - 1:
                        raise EjectError("in_use") from exc
                    time.sleep(RETRY_DELAY_S)
            self._ioctl(h, self.FSCTL_DISMOUNT_VOLUME)
            self._ioctl(h, self.IOCTL_STORAGE_EJECT_MEDIA)
        finally:
            self.k32.CloseHandle(h)

    def eject(self, letter: str) -> None:
        volume = f"\\\\.\\{letter}:"
        _kind, number = self.device_number(volume)
        disk = self.disk_node(number)
        media = self.k32.GetDriveTypeW(f"{letter}:\\") == self.DRIVE_REMOVABLE
        what, node = eject_target(disk, media, self.parent, self.describe)
        if what == DEVICE and node is not None:
            self.request_eject(node)
        elif what == MEDIA:
            self.eject_media(volume)
        else:
            raise EjectError("not_removable")
