# Academic Task 1 图表视觉基准集

该目录包含 10 张可重复生成的 Academic Task 1 图表。每张图有三个配套文件：

- `images/<id>.png`：发送给本地 Qwen 的图片。
- `<id>.json`：来源说明、原始数据、标准系列/类别、允许误差和标准答案。
- `results/<id>.json`：最近一次 Qwen 识别结果和逐项对比。

其中 4 张取自 World Bank 指标并在元数据中说明取整方式；另外 6 张是项目内控制变量样本，专门用于验证饼图、堆叠柱状图、表格和无数据标签折线图。控制变量样本不是官方真题，不能用来宣称真实考试题的识别效果。每个 JSON 都有 source_type 字段，区分公开来源数据与合成测试数据。

重新生成图像和运行验收：

```powershell
python scripts/generate_chart_benchmark.py
# 需要本机安装 Chrome；脚本生成 SVG 后用浏览器导出 PNG
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$svgDir = (Resolve-Path tests/fixtures/chart_benchmark/svg).Path
$pngDir = (Resolve-Path tests/fixtures/chart_benchmark/images).Path
Get-ChildItem $svgDir -Filter *.svg | ForEach-Object {
  $out = Join-Path $pngDir ($_.BaseName + ".png")
  & $chrome --headless --disable-gpu --hide-scrollbars --screenshot=$out --window-size=1400,900 ("file:///" + ($_.FullName -replace "\\", "/")) 2>$null | Out-Null
}
python scripts/run_chart_benchmark.py
```

折线图的点没有打印数值，标准答案的容差用于检查估读方向和大致范围；模型必须把这些点标为 `estimated`。柱状图、饼图和表格的数值直接打印在图上，允许误差为 0 或元数据中规定的取整误差。结果汇总在 `results/summary.json`。

