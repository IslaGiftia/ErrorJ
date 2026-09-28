/*
 * 下雨动画公共脚本：首页、小游戏、留言板、参考项目等页面共用同一份实现，
 * 参数（雨柱位置/时长/间隔、落点爆炸粒子）在这里统一维护，不要在各页面里另写一份。
 * 用法：页面里放好 #rainScene / #rainLayer / #rainFloor 三个元素并引入本文件即可，
 * 挂载时会自动初始化，重复引入不会重复创建雨柱。
 */
(function () {
  "use strict";

  function initRainScene() {
    var scene = document.getElementById("rainScene");
    var layer = document.getElementById("rainLayer");
    var floor = document.getElementById("rainFloor");
    if (!scene || !layer || !floor || !window.Element || !Element.prototype.animate) return;
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (scene.getAttribute("data-rain-ready") === "1") return;
    scene.setAttribute("data-rain-ready", "1");

    var beamOptions = [
      { left: 5, duration: 7, repeatDelay: 3, delay: 2 },
      { left: 18, duration: 3, repeatDelay: 3, delay: 4 },
      { left: 32, duration: 7, repeatDelay: 7, heightClass: "rain-beam--h6" },
      { left: 46, duration: 5, repeatDelay: 14, delay: 4 },
      { left: 60, duration: 11, repeatDelay: 2, heightClass: "rain-beam--h20" },
      { left: 75, duration: 4, repeatDelay: 2, heightClass: "rain-beam--h12" },
      { left: 92, duration: 6, repeatDelay: 4, delay: 2, heightClass: "rain-beam--h6" },
    ];

    function createBeamAnimation(beam) {
      var totalDuration = beam.options.duration + beam.options.repeatDelay;
      var fallOffset = beam.options.duration / totalDuration;
      var startY = -200;
      var endY = 1800;
      var startTransform = "translate3d(0px, " + startY + "px, 0) rotate(0deg)";
      var endTransform = "translate3d(0px, " + endY + "px, 0) rotate(0deg)";

      return beam.element.animate(
        [
          { transform: startTransform, offset: 0 },
          { transform: endTransform, offset: fallOffset },
          { transform: endTransform, offset: 1 },
        ],
        {
          duration: totalDuration * 1000,
          delay: (beam.options.delay || 0) * 1000,
          iterations: Infinity,
          easing: "linear",
          fill: "both",
        }
      );
    }

    function createExplosion(x, y) {
      var explosion = document.createElement("div");
      explosion.className = "rain-explosion";
      explosion.style.left = x + "px";
      explosion.style.top = y + "px";

      var flash = document.createElement("span");
      flash.className = "rain-explosion-flash";
      explosion.appendChild(flash);

      for (var i = 0; i < 20; i++) {
        var particle = document.createElement("span");
        particle.className = "rain-explosion-particle";
        particle.style.setProperty("--particle-x", Math.floor(Math.random() * 80 - 40) + "px");
        particle.style.setProperty("--particle-y", Math.floor(Math.random() * -50 - 10) + "px");
        particle.style.animationDuration = (Math.random() * 1.5 + 0.5) + "s";
        explosion.appendChild(particle);
      }

      layer.appendChild(explosion);
      return explosion;
    }

    function restartBeam(beam) {
      beam.animation.cancel();
      beam.animation = createBeamAnimation(beam);
    }

    var beams = beamOptions.map(function (options) {
      var element = document.createElement("div");
      element.className = "rain-beam" + (options.heightClass ? " " + options.heightClass : "");
      element.style.left = options.left + "%";
      element.setAttribute("aria-hidden", "true");
      layer.appendChild(element);

      var beam = {
        element: element,
        options: options,
        animation: null,
        cycling: false,
      };
      beam.animation = createBeamAnimation(beam);
      return beam;
    });

    window.setInterval(function () {
      var sceneRect = scene.getBoundingClientRect();
      var floorRect = floor.getBoundingClientRect();

      beams.forEach(function (beam) {
        if (beam.cycling) return;

        var beamRect = beam.element.getBoundingClientRect();
        if (beamRect.bottom < floorRect.top) return;

        beam.cycling = true;
        var relativeX = beamRect.left - sceneRect.left + beamRect.width / 2;
        var relativeY = beamRect.bottom - sceneRect.top;
        var explosion = createExplosion(relativeX, relativeY);

        window.setTimeout(function () {
          beam.cycling = false;
          restartBeam(beam);
        }, 2000);

        window.setTimeout(function () {
          explosion.remove();
        }, 3500);
      });
    }, 50);
  }

  window.ErrorRain = { init: initRainScene };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initRainScene);
  } else {
    initRainScene();
  }
})();
