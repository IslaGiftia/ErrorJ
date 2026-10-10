/* Error酱 通用上传区
 *
 * 一个上传入口同时支持：点击选择（Chromium 下用文件选择器，会记住上次打开的目录）、
 * 拖入文件、拖入文件夹（按深度递归，只挑符合类型的文件）。
 *
 * 用法：
 *   ErrorDropZone.attach(clickTarget, {
 *     input, dropTarget, accept: ["image/*", ".png"], maxCount, multiple,
 *     pickerId: "errorjiang-music", folder: true, depth: 3, toast, onFiles
 *   });
 *
 * 没有传 onFiles 时，会把文件写回 input.files 并触发 change，页面原有逻辑照常工作。
 */
(function () {
  var PICKER = typeof window.showOpenFilePicker === "function" ? window.showOpenFilePicker.bind(window) : null;
  var DIR_PICKER = typeof window.showDirectoryPicker === "function" ? window.showDirectoryPicker.bind(window) : null;
  var DEFAULT_DEPTH = 3;
  var SCAN_LIMIT = 600; // 防止拖进超大目录时卡死
  var TYPE_EXTS = {
    "image/*": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"],
    "audio/*": [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"]
  };

  function matchAccept(file, accept) {
    if (!accept || !accept.length) return true;
    var name = String(file.name || "").toLowerCase();
    var type = String(file.type || "").toLowerCase();
    for (var i = 0; i < accept.length; i++) {
      var token = String(accept[i] || "").trim().toLowerCase();
      if (!token) continue;
      if (token.charAt(0) === ".") {
        if (name.length >= token.length && name.slice(-token.length) === token) return true;
        continue;
      }
      if (token.indexOf("/*") > 0) {
        if (type.indexOf(token.slice(0, token.indexOf("/") + 1)) === 0) return true;
        continue;
      }
      if (type === token) return true;
    }
    return false;
  }

  // accept 列表转成文件选择器的 types，尽量让用户在系统弹窗里只看到能用的文件
  function pickerTypes(accept) {
    var mime = "";
    var exts = [];
    (accept || []).forEach(function (raw) {
      var token = String(raw || "").trim().toLowerCase();
      if (!token) return;
      if (token.charAt(0) === ".") {
        if (exts.indexOf(token) < 0) exts.push(token);
      } else if (!mime) {
        mime = token;
      } else if (mime !== token) {
        mime = ""; // 多个 MIME 组时不做限制，交给后面的类型过滤
      }
    });
    if (!mime && exts.length) mime = "application/octet-stream";
    if (!mime) return null;
    if (TYPE_EXTS[mime] && !exts.length) exts = TYPE_EXTS[mime].slice();
    var map = {};
    map[mime] = exts;
    return [{ description: "可上传的文件", accept: map }];
  }

  function readAllEntries(reader) {
    return new Promise(function (resolve) {
      var all = [];
      function step() {
        reader.readEntries(
          function (batch) {
            var list = Array.prototype.slice.call(batch || []);
            if (!list.length) {
              resolve(all);
              return;
            }
            all = all.concat(list);
            step();
          },
          function () {
            resolve(all);
          }
        );
      }
      step();
    });
  }

  function walkEntry(entry, opts, out, depth) {
    if (!entry || out.length >= SCAN_LIMIT) return Promise.resolve();
    if (entry.isFile) {
      return new Promise(function (resolve) {
        entry.file(
          function (file) {
            out.push(file);
            resolve();
          },
          function () {
            resolve();
          }
        );
      });
    }
    if (entry.isDirectory) {
      if (opts.folder === false) return Promise.resolve();
      if (depth >= (opts.depth || DEFAULT_DEPTH)) return Promise.resolve();
      return readAllEntries(entry.createReader()).then(function (children) {
        return children.reduce(function (chain, child) {
          return chain.then(function () {
            return walkEntry(child, opts, out, depth + 1);
          });
        }, Promise.resolve());
      });
    }
    return Promise.resolve();
  }

  function collectFiles(dataTransfer, opts) {
    opts = opts || {};
    var items = dataTransfer && dataTransfer.items;
    var entries = [];
    if (items && items.length && typeof DataTransferItem !== "undefined" && DataTransferItem.prototype.webkitGetAsEntry) {
      for (var i = 0; i < items.length; i++) {
        var item = items[i];
        if (!item || item.kind !== "file") continue;
        var entry = null;
        try {
          entry = item.webkitGetAsEntry();
        } catch (err) {
          entry = null;
        }
        if (entry) entries.push(entry);
      }
    }
    if (!entries.length) return Promise.resolve(Array.prototype.slice.call((dataTransfer && dataTransfer.files) || []));
    var out = [];
    return entries
      .reduce(function (chain, entry) {
        return chain.then(function () {
          return walkEntry(entry, opts, out, 0);
        });
      }, Promise.resolve())
      .then(function () {
        return out;
      });
  }

  function dedupe(files) {
    var seen = {};
    return files.filter(function (file) {
      var key = String(file.name || "") + ":" + String(file.size || 0) + ":" + String(file.lastModified || 0);
      if (seen[key]) return false;
      seen[key] = true;
      return true;
    });
  }

  function setInputFiles(input, files) {
    if (!input || typeof DataTransfer === "undefined") return false;
    try {
      var holder = new DataTransfer();
      files.forEach(function (file) {
        holder.items.add(file);
      });
      input.files = holder.files;
      return true;
    } catch (err) {
      return false;
    }
  }

  function fileListToArray(list) {
    return Array.prototype.slice.call(list || []);
  }

  function pickWithDialog(opts) {
    var keep = [];
    return PICKER({
      id: opts.pickerId || undefined,
      multiple: opts.multiple !== false,
      excludeAcceptAllOption: false,
      types: pickerTypes(opts.accept) || undefined
    }).then(function (handles) {
      return handles.reduce(function (chain, handle) {
        return chain.then(function () {
          return handle.getFile().then(function (file) {
            keep.push(file);
          });
        });
      }, Promise.resolve()).then(function () {
        return keep;
      });
    });
  }

  // showDirectoryPicker 返回的是 FileSystemDirectoryHandle，遍历方式和拖拽的 entry 不同
  async function collectFromDirectoryHandle(root, opts) {
    var out = [];
    var maxDepth = Number(opts.depth || DEFAULT_DEPTH);
    async function walk(dir, depth) {
      if (out.length >= SCAN_LIMIT) return;
      for await (var entry of dir.values()) {
        if (out.length >= SCAN_LIMIT) return;
        if (entry.kind === "file") {
          try {
            out.push(await entry.getFile());
          } catch (err) {}
        } else if (entry.kind === "directory" && depth < maxDepth) {
          await walk(entry, depth + 1);
        }
      }
    }
    await walk(root, 0);
    return out;
  }

  function pickDirectoryWithDialog(opts) {
    return DIR_PICKER({ id: opts.directoryId || opts.pickerId || undefined }).then(function (handle) {
      return collectFromDirectoryHandle(handle, opts);
    });
  }

  function notify(opts, message) {
    if (!message) return;
    if (typeof opts.toast === "function") opts.toast(message);
  }

  function attach(target, options) {
    var opts = options || {};
    var input = opts.input || null;
    var dropTarget = opts.dropTarget || target;
    var accept = opts.accept || [];
    var multiple = opts.multiple !== undefined ? Boolean(opts.multiple) : Boolean(input && input.multiple);
    var zone = { destroy: destroy, open: open };
    var depth = { depth: Number(opts.depth || DEFAULT_DEPTH) };

    // 上限可能被「工作台 → 上传限制」改掉，所以支持传函数实时取值
    function limit() {
      return Number(typeof opts.maxCount === "function" ? opts.maxCount() : opts.maxCount) || 0;
    }

    if (dropTarget && dropTarget.classList) dropTarget.classList.add("ej-dropzone");

    function deliver(files, info) {
      if (!files.length) {
        notify(opts, info && info.skipped ? "没有可上传的文件（已跳过 " + info.skipped + " 个不支持的文件）" : "");
        return;
      }
      if (typeof opts.onFiles === "function") {
        opts.onFiles(files, info);
        return;
      }
      if (!input) return;
      if (!setInputFiles(input, files)) {
        notify(opts, "当前浏览器不支持拖拽写入，请用点击选择。");
        return;
      }
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function acceptFiles(raw) {
      var all = dedupe(fileListToArray(raw));
      var accepted = all.filter(function (file) {
        return matchAccept(file, accept);
      });
      var skipped = all.length - accepted.length;
      var overflow = 0;
      var maxCount = limit();
      if (maxCount && accepted.length > maxCount) {
        overflow = accepted.length - maxCount;
        accepted = accepted.slice(0, maxCount);
      }
      var notes = [];
      if (skipped) notes.push("已跳过 " + skipped + " 个不支持的文件");
      if (overflow) notes.push("超过上限，只取前 " + maxCount + " 个");
      if (notes.length) notify(opts, notes.join("；"));
      deliver(accepted, { skipped: skipped, overflow: overflow, total: all.length });
    }

    function open() {
      if (opts.picker === false || !input) {
        if (input) input.click();
        return;
      }
      if (PICKER) {
        pickWithDialog({ pickerId: opts.pickerId, accept: accept, multiple: multiple })
          .then(function (files) {
            acceptFiles(files);
          })
          .catch(function (err) {
            if (err && err.name === "AbortError") return;
            input.click();
          });
        return;
      }
      input.click();
    }

    zone.openFolder = function () {
      if (!DIR_PICKER) {
        notify(opts, "当前浏览器不支持选择文件夹，可以把文件夹直接拖进来。");
        return;
      }
      pickDirectoryWithDialog({ pickerId: opts.pickerId, depth: depth.depth, directoryId: opts.directoryId })
        .then(function (files) {
          acceptFiles(files);
        })
        .catch(function (err) {
          if (err && err.name === "AbortError") return;
          notify(opts, "打开文件夹失败，可以把文件夹直接拖进来。");
        });
    };

    function onDragOver(event) {
      if (!event.dataTransfer) return;
      var types = event.dataTransfer.types || [];
      var hasFiles = Array.prototype.indexOf.call(types, "Files") >= 0;
      if (!hasFiles) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      if (dropTarget && dropTarget.classList) dropTarget.classList.add("is-dragover");
    }

    function onDragLeave(event) {
      if (!dropTarget) return;
      var next = event.relatedTarget;
      if (next && dropTarget.contains(next)) return;
      dropTarget.classList.remove("is-dragover");
    }

    function onDrop(event) {
      event.preventDefault();
      event.__ejDropHandled = true;
      if (dropTarget && dropTarget.classList) dropTarget.classList.remove("is-dragover");
      var dt = event.dataTransfer;
      if (!dt) return;
      collectFiles(dt, { depth: depth.depth, folder: opts.folder, maxCount: limit() }).then(acceptFiles);
    }

    if (dropTarget) {
      dropTarget.addEventListener("dragover", onDragOver);
      dropTarget.addEventListener("dragleave", onDragLeave);
      dropTarget.addEventListener("drop", onDrop);
    }
    if (target) {
      target.addEventListener("click", function (event) {
        if (event.target.closest && event.target.closest("[data-dropzone-skip]")) return;
        event.preventDefault();
        open();
      });
    }

    function destroy() {
      if (dropTarget) {
        dropTarget.removeEventListener("dragover", onDragOver);
        dropTarget.removeEventListener("dragleave", onDragLeave);
        dropTarget.removeEventListener("drop", onDrop);
        dropTarget.classList.remove("is-dragover", "ej-dropzone");
      }
    }

    return zone;
  }

  // 拖到页面其它地方时不要让浏览器直接打开文件
  document.addEventListener("dragover", function (event) {
    var types = (event.dataTransfer && event.dataTransfer.types) || [];
    if (Array.prototype.indexOf.call(types, "Files") >= 0) event.preventDefault();
  });
  document.addEventListener("drop", function (event) {
    if (event.__ejDropHandled) return;
    var types = (event.dataTransfer && event.dataTransfer.types) || [];
    if (Array.prototype.indexOf.call(types, "Files") >= 0) event.preventDefault();
  });

  window.ErrorDropZone = {
    attach: attach,
    matchAccept: matchAccept,
    collect: collectFiles,
    pickerSupported: Boolean(PICKER),
    directorySupported: Boolean(DIR_PICKER)
  };
})();
