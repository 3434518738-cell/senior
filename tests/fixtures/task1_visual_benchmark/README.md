# IELTS Academic Task 1 流程图与地图控制基准

此目录提供可重复的视觉理解控制测试：3 张流程图、3 张前后对比地图。
所有图片均由项目脚本生成，**不是 IELTS 官方题目或考场真题**。

每张图片都有对应 JSON，记录预设答案；`results/` 保存本地 Qwen 最近一次识别和逐项评估结果。图片分类、流程步骤标签/顺序/箭头关系，以及地图改造位置和前后状态分别评估。

重新生成 SVG、JSON 答案和 PNG：

```powershell
python scripts/generate_visual_benchmark.py
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$svgDir = (Resolve-Path tests/fixtures/task1_visual_benchmark/svg).Path
$pngDir = (Resolve-Path tests/fixtures/task1_visual_benchmark/images).Path
Get-ChildItem $svgDir -Filter *.svg | ForEach-Object {
  $out = Join-Path $pngDir ($_.BaseName + '.png')
  & $chrome --headless --disable-gpu --hide-scrollbars --screenshot=$out `
    --window-size=1400,1100 ("file:///" + ($_.FullName -replace '\\', '/')) 2>$null | Out-Null
}
```

运行本地模型并汇总验收：

```powershell
python scripts/run_visual_benchmark.py
```

当前 Qwen3.5 本地结果：类型分类 6/6；流程图节点文本 14/15，边关系 12/12；地图变化 9/9、对应的前后描述字段 18/18。流程图步骤顺序整图准确为 2/3；包含分支的图中，模型识别了所有箭头关系，但漏读了一个分支终点的方框标签。地图“变化”指标仅核对实际发生变化的位置，不把原样保留的位置算作一项变化。

这些结果只说明模型在这 6 张清晰、规则、合成图片上的当前表现，不能代表真实 IELTS 图片、低清照片、复杂地图、评分准确率或考生分数。真实用户图片接入评分前仍应提供读图结果核对步骤；未确认的图像事实不能被当成无误的扣分依据。
