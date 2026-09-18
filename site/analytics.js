/* Google Analytics 4 for homeroom.chelseakr.com. Added to the published pages by
   homeroom.analytics (owner decision, 2026-09-17). Loads nothing off the production
   host, under Global Privacy Control or Do Not Track, or after "Opt out of
   analytics". */
(function () {
  "use strict";
  var ID = "G-PMC113MW2C";
  var HOST = "homeroom.chelseakr.com";
  var KEY = "homeroom.chelseakr.com:analytics-opt-out";
  var REGIONS = ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "AX", "GF", "GP", "MQ", "MF", "RE", "YT", "IS", "LI", "NO", "GB", "CH"];
  var LABELS = {"en": {"off": "Analytics is off in this browser.", "on": "Analytics is back on.", "optIn": "Opt back in", "optOut": "Opt out of analytics"}, "es": {"off": "Las analíticas están desactivadas en este navegador.", "on": "Las analíticas están activadas de nuevo.", "optIn": "Volver a activarlas", "optOut": "Desactivar las analíticas"}};
  var w = window;
  var d = document;
  var n = navigator;

  function signal() {
    if (n.globalPrivacyControl === true) return true;
    var dnt = n.doNotTrack || w.doNotTrack || n.msDoNotTrack;
    return dnt === "1" || dnt === "yes";
  }
  function stored() {
    try {
      return w.localStorage.getItem(KEY) === "1";
    } catch (e) {
      return false;
    }
  }
  function optedOut() {
    return signal() || stored();
  }
  function scrubbedPath(path) {
    return path.split("/").map(function (part) {
      return part === "" || (part.length <= 100 && /^[a-z0-9]+(?:[-_.][a-z0-9]+)*$/i.test(part))
        ? part : ":redacted";
    }).join("/");
  }
  function campaign(search) {
    var kept = [];
    var keys = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id"];
    var params = new URLSearchParams(search);
    for (var i = 0; i < keys.length; i++) {
      var value = params.get(keys[i]);
      if (value) kept.push(keys[i] + "=" + encodeURIComponent(value.slice(0, 100)));
    }
    return kept.length ? "?" + kept.join("&") : "";
  }
  function referrer() {
    if (!d.referrer) return "";
    try {
      var url = new URL(d.referrer);
      if (url.origin === w.location.origin) return url.origin + scrubbedPath(url.pathname) + campaign(url.search);
      return url.origin + "/";
    } catch (e) {
      return "";
    }
  }
  function clearCookies() {
    var own = { _ga: true };
    own["_ga_" + ID.slice(2)] = true;
    var labels = w.location.hostname.split(".");
    var domains = [""];
    for (var i = 0; i < labels.length - 1; i++) domains.push(labels.slice(i).join("."));
    d.cookie.split(";").forEach(function (pair) {
      var name = pair.split("=")[0].trim();
      if (!own[name]) return;
      domains.forEach(function (domain) {
        d.cookie = name + "=; Max-Age=0; path=/" + (domain ? "; domain=" + domain : "");
      });
    });
  }

  var loaded = false;
  function load() {
    if (loaded || !ID || w.location.hostname !== HOST || optedOut()) return false;
    loaded = true;
    Object.defineProperty(w, "ga-disable-" + ID, { configurable: true, get: optedOut });
    var layer = (w.dataLayer = w.dataLayer || []);
    function gtag() {
      layer.push(arguments);
    }
    gtag("consent", "default", {
      ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied",
      analytics_storage: "denied", region: REGIONS
    });
    gtag("consent", "default", {
      ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied",
      analytics_storage: "granted"
    });
    gtag("set", "ads_data_redaction", true);
    gtag("js", new Date());
    gtag("config", ID, {
      send_page_view: false, allow_google_signals: false, allow_ad_personalization_signals: false
    });
    var page = {
      page_location: w.location.origin + scrubbedPath(w.location.pathname) + campaign(w.location.search),
      page_title: d.title.slice(0, 300)
    };
    var from = referrer();
    if (from) page.page_referrer = from;
    gtag("set", page);
    gtag("event", "page_view");
    var script = d.createElement("script");
    script.async = true;
    script.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(ID);
    d.head.appendChild(script);
    return true;
  }

  function storageWorks() {
    try {
      var current = w.localStorage.getItem(KEY);
      w.localStorage.setItem(KEY, current === null ? "0" : current);
      if (current === null) w.localStorage.removeItem(KEY);
      return true;
    } catch (e) {
      return false;
    }
  }
  function renderControls(changed) {
    var slots = d.querySelectorAll(".analytics-opt-out");
    var off = stored();
    for (var i = 0; i < slots.length; i++) {
      var slot = slots[i];
      var holder = slot.closest("[lang]");
      var labels = LABELS[holder && LABELS[holder.getAttribute("lang")] ? holder.getAttribute("lang") : "en"];
      var button = slot.querySelector("button");
      var status = slot.querySelector("[role=status]");
      if (!button) {
        button = d.createElement("button");
        button.type = "button";
        button.style.font = "inherit";
        button.style.minHeight = "24px";
        button.style.marginInlineStart = "0.5em";
        button.style.cursor = "pointer";
        button.addEventListener("click", toggle);
        status = d.createElement("span");
        status.setAttribute("role", "status");
        status.style.marginInlineStart = "0.5em";
        slot.appendChild(button);
        slot.appendChild(status);
      }
      button.textContent = off ? labels.optIn : labels.optOut;
      status.textContent = off ? labels.off : changed ? labels.on : "";
      slot.hidden = false;
    }
  }
  function toggle() {
    var optOut = !stored();
    try {
      if (optOut) w.localStorage.setItem(KEY, "1");
      else w.localStorage.removeItem(KEY);
    } catch (e) {
      return;
    }
    if (optOut) clearCookies();
    else load();
    renderControls(true);
  }

  if (optedOut() && ID) clearCookies();
  load();
  if (storageWorks()) renderControls(false);
})();
