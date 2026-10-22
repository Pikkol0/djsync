/**
 * DJSync — réception des retours (onglet « Retours » de l'application) → e-mail.
 *
 * À coller dans un projet Google Apps Script (script.google.com) du compte Gmail qui doit recevoir
 * les retours, puis à déployer en « Application Web » (Exécuter en tant que : moi ; Accès : tout le
 * monde). Guide pas à pas : docs/FEEDBACK_SETUP.fr.md.
 *
 * Ce que fait le script : reçoit un JSON de DJSync, vérifie les limites (taille, nombre d'envois),
 * et envoie UN e-mail par envoi, avec les remarques numérotées et les captures en pièces jointes.
 * Rien n'est stocké. Quotas d'un compte Gmail gratuit : ~100 e-mails par jour.
 */

// ---- réglages ------------------------------------------------------------------------------
var OWNER = Session.getEffectiveUser().getEmail();  // destinataire : le compte qui déploie le script
var MAX_PER_CLIENT_PER_DAY = 10;                    // un même ordinateur, par tranche de 6 h
var MAX_PER_DAY = 60;                               // tous les envois confondus, par tranche de 6 h
var MAX_BYTES = 15 * 1024 * 1024;                   // taille maximale d'un envoi
var MAX_ITEMS = 10;
var MAX_IMAGES = 3;

var KIND = {bug: "Bug", idea: "Idée", comment: "Commentaire"};

function doPost(e) {
  try {
    var raw = (e && e.postData && e.postData.contents) || "";
    if (raw.length > MAX_BYTES * 1.4) return reply_({ok: false, error: "too_big"});
    var data = JSON.parse(raw);
    var items = (data.items || []).slice(0, MAX_ITEMS);
    if (!items.length) return reply_({ok: false, error: "empty"});
    if (!allow_(String(data.client || "anonymous"))) return reply_({ok: false, error: "limit"});

    var info = data.info || {};
    var subjectKinds = {};
    var html = [];
    var attachments = [];
    html.push("<p><b>DJSync " + esc_(info.version || "?") + "</b> · " + esc_(info.os || "") +
              (info.library ? " · " + esc_(info.library) : "") + "</p>");
    if (data.email) html.push("<p>Répondre à : " + esc_(data.email) + "</p>");
    items.forEach(function (it, i) {
      var kind = KIND[it.kind] || "Remarque";
      subjectKinds[kind] = (subjectKinds[kind] || 0) + 1;
      html.push("<h3>" + (i + 1) + ". [" + kind + "] " + esc_(it.title || "(sans titre)") + "</h3>");
      html.push("<pre style='white-space:pre-wrap;font-family:inherit'>" + esc_(it.text || "") + "</pre>");
      (it.images || []).slice(0, MAX_IMAGES).forEach(function (img) {
        attachments.push(Utilities.newBlob(Utilities.base64Decode(img.data), img.mime || "image/jpeg",
                                           img.name || ("capture-" + (i + 1) + ".jpg")));
        html.push("<p>📎 " + esc_(img.name || "capture") + "</p>");
      });
    });
    if (data.log) {
      attachments.push(Utilities.newBlob(data.log, "text/plain", "djsync-log.txt"));
      html.push("<p>📎 djsync-log.txt (fin du journal, chemins personnels masqués)</p>");
    }
    var kinds = Object.keys(subjectKinds).map(function (k) { return subjectKinds[k] + " " + k; }).join(", ");
    var first = items[0].title || "";
    var options = {htmlBody: html.join("\n"), attachments: attachments, name: "DJSync"};
    if (data.email && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(data.email)) options.replyTo = data.email;
    MailApp.sendEmail(OWNER, "[DJSync " + (info.version || "") + "] " + kinds + (first ? " · " + first : ""),
                      "Voir la version HTML de cet e-mail.", options);
    return reply_({ok: true});
  } catch (err) {
    console.error(err);
    return reply_({ok: false, error: "server"});
  }
}

function doGet() {
  return reply_({ok: true, service: "djsync-feedback"});
}

// Limites d'envoi : par ordinateur et au total, par tranche de 6 h (durée maximale du cache du script).
function allow_(client) {
  var cache = CacheService.getScriptCache();
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var keyC = "c:" + client.slice(0, 64), keyAll = "all";
    var c = Number(cache.get(keyC) || 0), all = Number(cache.get(keyAll) || 0);
    if (c >= MAX_PER_CLIENT_PER_DAY || all >= MAX_PER_DAY) return false;
    cache.put(keyC, String(c + 1), 21600);   // 6 h (durée maximale du cache) : limite approchée
    cache.put(keyAll, String(all + 1), 21600);
    return true;
  } finally {
    lock.releaseLock();
  }
}

function reply_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function esc_(s) {
  return String(s).replace(/[&<>"]/g, function (c) {
    return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c];
  });
}
