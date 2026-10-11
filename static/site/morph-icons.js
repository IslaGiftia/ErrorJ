/*
 * morphicons 适配层：把「按钮换图标」从硬切换成 stroke 形变。
 *
 * 站点没有构建步骤，所以直接 import vendored 的 ESM（内部引用都是相对路径）。
 * 图标数据直接取站点已有的 window.lucide.icons（IconNode），不额外引一份。
 *
 * 约定：ErrorMorph.morph(el, "pause") 返回 true 表示这次切换由形变接管；
 * 返回 false（模块没加载出来 / 图标数据缺失 / 浏览器太老）时，调用方按原来的
 * lucide 渲染走，保证降级后界面完全照旧。
 */
import { createMorph } from "/static/vendor/morphicons/dom.js";
// 自己带上这几个图标的数据：首页（site.html）根本没加载 lucide，
// 只依赖 window.lucide 的话主题按钮就接管不了。数据与 lucide 同源，见该文件的注释。
import { ICON_DATA } from "/static/vendor/morphicons/icon-data.js";

var REDUCED_MOTION = "user"; // 跟随系统「减少动效」：开了就直接切，不做形变
var SPRING = "smooth"; // 临界阻尼、无回弹——这是工具型界面，不要俏皮
var registry = new WeakMap();

function pascal(name) {
  return String(name || "")
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map(function (part) {
      return part.charAt(0).toUpperCase() + part.slice(1);
    })
    .join("");
}

function iconData(name) {
  var key = pascal(name);
  if (ICON_DATA[key]) return ICON_DATA[key];
  var icons = window.lucide && window.lucide.icons;
  return (icons && icons[key]) || null;
}

function buildSvg(name) {
  var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  // 属性照抄 lucide 的输出，这样各页已有的 SVG 尺寸/描边/颜色规则照旧生效
  svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  svg.setAttribute("width", "24");
  svg.setAttribute("height", "24");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  // 带上 lucide 类名让样式接上；不带 data-lucide，免得被 createIcons() 当占位符重建掉
  svg.setAttribute("class", "lucide morph-icon lucide-" + name);
  var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  svg.appendChild(path);
  return { svg: svg, path: path };
}

function ensure(host, name) {
  var entry = registry.get(host);
  if (entry) return entry;
  var data = iconData(name);
  if (!data) return null;

  var built = buildSvg(name);
  // 「图标 + 文字」的按钮（例如音乐编辑页的删除）只替换图标节点，保留文字
  var placeholder = host.querySelector("svg, i[data-lucide]");
  if (placeholder) placeholder.replaceWith(built.svg);
  else {
    host.textContent = "";
    host.appendChild(built.svg);
  }

  entry = {
    path: built.path,
    svg: built.svg,
    morph: createMorph(built.path, data, { reducedMotion: REDUCED_MOTION }),
    name: name
  };
  registry.set(host, entry);
  return entry;
}

function apply(host, name, animate) {
  if (!host || !iconData(name)) return false;
  var entry = ensure(host, name);
  if (!entry) return false;
  if (entry.name === name) return true; // 状态没变，别白跑一次动画
  // 类名跟着状态走（.lucide-<name>），跟 lucide 渲染的静态图标保持一致，便于排查和样式挂钩
  if (entry.svg) entry.svg.setAttribute("class", "lucide morph-icon lucide-" + name);
  entry.name = name;
  if (animate) entry.morph.morphTo(iconData(name), SPRING);
  else entry.morph.set(iconData(name));
  return true;
}

window.ErrorMorph = {
  ready: true,
  morph: function (host, name) {
    return apply(host, name, true);
  },
  set: function (host, name) {
    return apply(host, name, false);
  }
};

/*
 * 接管「已经是静态图标」的按钮：首屏由各自的脚本先渲染成 lucide 图标，
 * 模块晚一步加载，这里按当前状态建好 morph 实例，第一次点击就能形变，
 * 而不是等第二次才动画。
 */
(function boot() {
  var hosts = document.querySelectorAll("[data-icon]");
  Array.prototype.forEach.call(hosts, function (host) {
    var name = host.getAttribute("data-icon");
    if (name && iconData(name)) apply(host, name, false);
  });
  var glyph = document.getElementById("themeGlyph");
  if (glyph) {
    var dark = document.documentElement.getAttribute("data-theme") === "dark";
    apply(glyph, dark ? "moon" : "sun", false);
  }
})();
