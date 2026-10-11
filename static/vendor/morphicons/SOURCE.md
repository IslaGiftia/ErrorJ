# morphicons（vendored）

- 来源：https://github.com/guillermolg00/morphicons
- 版本：1.7.1（npm `morphicons@1.7.1` 的 `dist/`）
- 许可：MIT（见同目录 `LICENSE`）
- 文件：`dom.js`、`spring-CFHloqPP.js`、`normalize-CYnN3Npw.js`
  （只有 `morphicons/dom` 这条入口用到的三个文件；3.5 个文件里其余入口没 vendored）
- 为什么原样放进来：站点没有构建步骤，这几个文件内部引用都是相对路径，
  浏览器可以直接 `import`，不需要 importmap，也没有裸模块引用。
- 用法见 `static/site/morph-icons.js`。
