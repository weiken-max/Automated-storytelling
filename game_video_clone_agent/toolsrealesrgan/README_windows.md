# RealESRGAN

本目录提供以下模型：

1. realesr-animevideov3（默认）
2. realesrgan-x4plus
3. realesrgan-x4plus-anime

命令示例：

1. ./realesrgan-ncnn-vulkan.exe -i input.jpg -o output.png
2. ./realesrgan-ncnn-vulkan.exe -i input.jpg -o output.png -n realesr-animevideov3
3. ./realesrgan-ncnn-vulkan.exe -i input_folder -o outputfolder -n realesr-animevideov3 -s 2 -f jpg
4. ./realesrgan-ncnn-vulkan.exe -i input_folder -o outputfolder -n realesr-animevideov3 -s 4 -f jpg


增强动漫视频的流程：

1. 使用 ffmpeg 从视频中抽取帧（请事先创建文件夹 `tmp_frames`）

    ffmpeg -i onepiece_demo.mp4 -qscale:v 1 -qmin 1 -qmax 1 -vsync 0 tmp_frames/frame%08d.jpg

2. 使用 Real-ESRGAN 可执行文件做推理（请事先创建文件夹 `out_frames`）

    ./realesrgan-ncnn-vulkan.exe -i tmp_frames -o out_frames -n realesr-animevideov3 -s 2 -f jpg

3. 将增强后的帧合并回视频

    ffmpeg -i out_frames/frame%08d.jpg -i onepiece_demo.mp4 -map 0:v:0 -map 1:a:0 -c:a copy -c:v libx264 -r 23.98 -pix_fmt yuv420p output_w_audio.mp4

------------------------

GitHub: https://github.com/xinntao/Real-ESRGAN/
论文: https://arxiv.org/abs/2107.10833

------------------------

本可执行文件为**便携版**，已包含所需二进制与模型，无需安装 CUDA 或 PyTorch 环境。

注意：由于该程序会先将输入图像裁成多个 tile 分别处理再拼接，可能会出现块状不一致，且与 PyTorch 版结果略有差异。

本可执行文件基于 [Tencent/ncnn](https://github.com/Tencent/ncnn) 以及 [nihui](https://github.com/nihui) 的 [realsr-ncnn-vulkan](https://github.com/nihui/realsr-ncnn-vulkan)。
