// Fit the 1280x720 stage to the window, and move between slides with the arrow keys,
// Page Up/Down or space. The previous/next links in each slide's footer do the same.
(function () {
  var stage = document.querySelector(".stage");
  function fit() {
    var k = Math.min(window.innerWidth / 1280, window.innerHeight / 720) * 0.98;
    stage.style.transformOrigin = "center center";
    stage.style.transform = "translate(-50%, -50%) scale(" + k + ")";
  }
  window.addEventListener("resize", fit);
  fit();
  function go(rel) {
    var a = document.querySelector('a[rel="' + rel + '"]');
    if (a && a.getAttribute("href")) location.href = a.href;
  }
  document.addEventListener("keydown", function (e) {
    if (["ArrowRight", "PageDown", " "].indexOf(e.key) >= 0) { e.preventDefault(); go("next"); }
    if (["ArrowLeft", "PageUp"].indexOf(e.key) >= 0) { e.preventDefault(); go("prev"); }
  });
})();
