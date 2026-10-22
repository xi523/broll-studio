# 运行与分发

需要可执行 Python 的电脑/智能体；纯文本聊天窗口不能直接运行。无 API key、无模型版本检查，首次安装依赖需要联网。

Python 3.9+，建议独立环境：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r "$SKILL_DIR/scripts/requirements.txt"
.venv/bin/python "$SKILL_DIR/scripts/broll.py" validate plan.json
```

Windows 用 `py -3 -m venv .venv` 和 `.venv\Scripts\python.exe`，不要改用户全局依赖。

Pillow 绘制，NumPy 数学，fonttools 检查字形，imageio-ffmpeg 提供常见平台 FFmpeg。若没有适用二进制，将 `BROLL_FFMPEG` 设为已有 FFmpeg 绝对路径。依赖范围见 requirements.txt，实际验证版本见发布报告。

## 命令

```sh
python scripts/broll.py styles
python scripts/broll.py validate plan.json
python scripts/broll.py preview plan.json --out previews
python scripts/broll.py render plan.json --out output
python scripts/broll.py render plan.json --out output --font /path/to/font.ttf
```

默认拒绝覆盖已有 MP4；明确需要替换时加 `--overwrite`。预览每场景三张 JPG。成片包括独立 MP4、合辑 broll.mp4、参数快照、时间映射与报告；失败留下的 `.partial.mp4` 不是成片。

素材相对路径以 plan.json 所在目录为根。输出目录可含空格与中文。输出的 plan.json 副本仍引用原项目素材；交付需一起复制素材并核对路径。

## 音频与时间

默认无声。`audio` 文件从 `start` 秒开始贴到合辑零点；短音轨补静音，长音轨截断。只适用于已准备好的连续配音。

`source_start/source_end` 是插回原口播的剪辑标记；不会据此自动剪拼原录音。多个非连续片段不能直接把完整口播放到合辑下当作对齐完成。应按标记插回原视频或先准备对应音轨。

最终时长按帧数四舍五入（小于半帧误差），实际时间写入 timing.json。需要逐字对齐时用实测转写时间安排事件并回看。

## 字体

随包带得意黑和 Noto Serif CJK SC，保留许可证。暗底暖金、柠檬黄科技、水墨默认衬线，其余用得意黑。`--font` 或根级 `font` 可替换；缺字报错。

默认覆盖主要中文与拉丁字母，不保证所有语言/emoji。阿拉伯语、印地语等需相应字体与 RAQM/Pango/HarfBuzz 排版支持，不能宣称全部验证。

## 边界

产品图片是平面展示，不重建背面；ring/knot 是显式选择的几何示意。水墨为程序分层画，立体为简化光照。需要更高质感时用扩展组件和用户素材。
