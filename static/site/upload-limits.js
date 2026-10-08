/* 读取工作台配置的上传大小与数量限制，失败时回退到内置默认值。 */
(function (global) {
  "use strict";

  var DEFAULTS = {
    message_file: {
      max_count: 3,
      max_file_bytes: 5 * 1024 * 1024,
      max_total_bytes: 15 * 1024 * 1024,
    },
    moment_image: {
      max_count: 9,
      max_file_bytes: 5 * 1024 * 1024,
      max_total_bytes: 15 * 1024 * 1024,
    },
    music_file: { max_count: 20, max_file_bytes: 60 * 1024 * 1024 },
    book_file: { max_count: 20, max_file_bytes: 60 * 1024 * 1024 },
    site_photo: { max_count: 20, max_file_bytes: 15 * 1024 * 1024 },
    recommend_image: { max_count: 1, max_file_bytes: 15 * 1024 * 1024 },
    map_photo: { max_count: 9, max_file_bytes: 8 * 1024 * 1024 },
    note_image: { max_count: 20, max_file_bytes: 20 * 1024 * 1024 },
    note_import: { max_count: 1, max_file_bytes: 20 * 1024 * 1024 },
    workbench_source: { max_count: 1, max_file_bytes: 30 * 1024 * 1024 },
    workbench_firmware: { max_count: 1, max_file_bytes: 30 * 1024 * 1024 },
    workbench_document: { max_count: 1, max_file_bytes: 30 * 1024 * 1024 },
    workbench_image: { max_count: 1, max_file_bytes: 30 * 1024 * 1024 },
    workbench_other: { max_count: 1, max_file_bytes: 30 * 1024 * 1024 },
    part_image: { max_count: 1, max_file_bytes: 5 * 1024 * 1024 },
  };

  var cache = null;
  var pending = null;

  function clone(value) {
    var copy = {};
    Object.keys(value || {}).forEach(function (key) {
      copy[key] = value[key];
    });
    return copy;
  }

  function merge(key, value) {
    var base = clone(DEFAULTS[key]);
    if (!value || typeof value !== "object") return base;
    ["max_count", "max_file_bytes", "max_total_bytes"].forEach(function (field) {
      var number = Number(value[field]);
      if (isFinite(number) && number > 0) base[field] = number;
    });
    if (
      base.max_total_bytes &&
      base.max_file_bytes &&
      base.max_total_bytes < base.max_file_bytes
    ) {
      base.max_total_bytes = base.max_file_bytes;
    }
    return base;
  }

  function normalize(limits) {
    var result = {};
    Object.keys(DEFAULTS).forEach(function (key) {
      result[key] = merge(key, limits && limits[key]);
    });
    return result;
  }

  function ready() {
    if (cache) return Promise.resolve(cache);
    if (pending) return pending;
    pending = fetch("/api/site/upload-limits", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (data) {
        cache = normalize(data && data.limits);
        return cache;
      })
      .catch(function () {
        cache = normalize(null);
        return cache;
      })
      .then(function (result) {
        pending = null;
        return result;
      });
    return pending;
  }

  function get(key) {
    var source = cache && cache[key];
    return clone(source || DEFAULTS[key] || {});
  }

  function bytes(key, field) {
    var value = get(key)[field || "max_file_bytes"];
    return Number(value) || 0;
  }

  function count(key) {
    return Number(get(key).max_count) || 1;
  }

  function megabytes(value) {
    var number = Number(value || 0) / (1024 * 1024);
    if (!isFinite(number) || number <= 0) return 0;
    return Math.round(number * 10) / 10;
  }

  function label(value) {
    var number = megabytes(value);
    return (Number.isInteger(number) ? String(number) : number.toFixed(1)) + "MB";
  }

  function apply(callback) {
    return ready().then(function (limits) {
      callback(limits);
      return limits;
    });
  }

  global.ErrorUploadLimits = {
    DEFAULTS: DEFAULTS,
    ready: ready,
    get: get,
    bytes: bytes,
    count: count,
    megabytes: megabytes,
    label: label,
    apply: apply,
  };
})(window);
