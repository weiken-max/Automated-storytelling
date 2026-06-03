import re
from pathlib import Path

html_path = Path("palette_studio.html")
html = html_path.read_text(encoding="utf-8")

# PATCH 2 - triggerShake
old_shake = """        const response = await fetch("http://127.0.0.1:8000/api/story/v1/compile", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            app_id: "palette-cinema-id",
            mode_path: "BLUE",
            original_text: "请为我随机生成一个赛博朋克废土风格的电影梗概故事大纲。",
            pipeline_config: {
              polish_flow: { enabled: true, system_prompt: state.presets.outline },
              voiceover_flow: { system_prompt: state.presets.voiceover },
              render_flow: { style_presets: state.presets.image, seed: 12345 }
            }
          })
        });
        const res = await response.json();"""

new_shake = """        const res = await pywebview.api.compile_story({
            app_id: "palette-cinema-id",
            mode_path: "BLUE",
            original_text: "请为为我随机生成一个赛博朋克废土风格的电影梗概故事大纲。",
            pipeline_config: {
              polish_flow: { enabled: true, system_prompt: state.presets.outline },
              voiceover_flow: { system_prompt: state.presets.voiceover },
              render_flow: { style_presets: state.presets.image, seed: 12345 }
            }
          });"""

# Since original_text might have typo or not, let's do a more robust substring matching or replace.
# Let's check if old_shake is in html. If not, we will print error.
if old_shake not in html:
    # Try with double or single spaces
    print("WARNING: Exact old_shake not found, trying fuzzy replacement...")
    # We will replace the fetch part of triggerShake
    pattern = r'const\s+response\s*=\s*await\s+fetch\("http://127\.0\.0\.1:8000/api/story/v1/compile".*?\);\s*const\s+res\s*=\s*await\s+response\.json\(\);'
    html, count = re.subn(pattern, """const res = await pywebview.api.compile_story({
            app_id: "palette-cinema-id",
            mode_path: "BLUE",
            original_text: "请为我随机生成一个赛博朋克废土风格的电影梗概故事大纲。",
            pipeline_config: {
              polish_flow: { enabled: true, system_prompt: state.presets.outline },
              voiceover_flow: { system_prompt: state.presets.voiceover },
              render_flow: { style_presets: state.presets.image, seed: 12345 }
            }
          });""", html, flags=re.DOTALL)
    print(f"Fuzzy triggerShake replaced: {count} occurrences")
else:
    html = html.replace(old_shake, new_shake)
    print("Exact triggerShake replaced.")

# PATCH 3 - handleC1Launch compile
old_c1_launch = """        const compRes = await fetch("http://127.0.0.1:8000/api/story/v1/compile", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            app_id: "palette-cinema-id",
            mode_path: state.modePath,
            original_text: text,
            pipeline_config: {
              polish_flow: {
                enabled: state.polishEnabled,
                system_prompt: state.polishEnabled ? state.presets.polish : "",
                immutable_lock: !state.polishEnabled
              },
              voiceover_flow: { system_prompt: state.presets.voiceover },
              render_flow: { style_presets: state.presets.image, seed: state.seed }
            }
          })
        });
        
        const cData = await compRes.json();
        if (cData.status !== "success") {
          throw new Error("编译旁白接口返回异常");
        }"""

new_c1_launch = """        const cData = await pywebview.api.compile_story({
            app_id: "palette-cinema-id",
            mode_path: state.modePath,
            original_text: text,
            pipeline_config: {
              polish_flow: {
                enabled: state.polishEnabled,
                system_prompt: state.polishEnabled ? state.presets.polish : "",
                immutable_lock: !state.polishEnabled
              },
              voiceover_flow: { system_prompt: state.presets.voiceover },
              render_flow: { style_presets: state.presets.image, seed: state.seed }
            }
          });
        if (cData.status !== "success") {
          throw new Error(cData.detail || "剧本编译失败");
        }"""

if old_c1_launch not in html:
    print("WARNING: Exact old_c1_launch not found, trying fuzzy replacement...")
    pattern = r'const\s+compRes\s*=\s*await\s+fetch\("http://127\.0\.0\.1:8000/api/story/v1/compile".*?\);\s*const\s+cData\s*=\s*await\s+compRes\.json\(\);\s*if\s*\(cData\.status\s*!==\s*"success"\)\s*\{\s*throw\s+new\s+Error\("编译旁白接口返回异常"\);\s*\}'
    html, count = re.subn(pattern, new_c1_launch, html, flags=re.DOTALL)
    print(f"Fuzzy handleC1Launch replaced: {count} occurrences")
else:
    html = html.replace(old_c1_launch, new_c1_launch)
    print("Exact handleC1Launch replaced.")

# PATCH 4 - generate_assets
old_gen_assets = """        const assetRes = await fetch("http://127.0.0.1:8000/api/assets/v1/generate", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            entities: state.extractedEntities,
            global_style_prompt: state.presets.image,
            seed: state.seed
          })
        });
        
        clearInterval(logTimer);
        const aData = await assetRes.json();
        if (aData.status !== "success") {
          throw new Error("资产定妆照生图接口返回异常");
        }"""

new_gen_assets = """        const aData = await pywebview.api.generate_assets({
            entities: state.extractedEntities,
            global_style_prompt: state.presets.image,
            seed: state.seed
          });
        clearInterval(logTimer);
        if (aData.status !== "success") {
          throw new Error(aData.detail || "定妆照生图失败");
        }"""

if old_gen_assets not in html:
    print("WARNING: Exact old_gen_assets not found, trying fuzzy replacement...")
    pattern = r'const\s+assetRes\s*=\s*await\s+fetch\("http://127\.0\.0\.1:8000/api/assets/v1/generate".*?\);\s*clearInterval\(logTimer\);\s*const\s+aData\s*=\s*await\s+assetRes\.json\(\);\s*if\s*\(aData\.status\s*!==\s*"success"\)\s*\{\s*throw\s+new\s+Error\("资产定妆照生图接口返回异常"\);\s*\}'
    html, count = re.subn(pattern, new_gen_assets, html, flags=re.DOTALL)
    print(f"Fuzzy generate_assets replaced: {count} occurrences")
else:
    html = html.replace(old_gen_assets, new_gen_assets)
    print("Exact generate_assets replaced.")

# PATCH 5 - rebuildAssetCard
old_rebuild_asset = """        const response = await fetch("http://127.0.0.1:8000/api/render/v1/single-frame", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            target_id: ast.id,
            prompt: newPrompt,
            seed: state.seed,
            style_lock: true
          })
        });
        const res = await response.json();"""

new_rebuild_asset = """        const res = await pywebview.api.render_single_frame({
            target_id: ast.id,
            prompt: newPrompt,
            seed: state.seed,
            style_lock: true
          });"""

if old_rebuild_asset not in html:
    print("WARNING: Exact old_rebuild_asset not found, trying fuzzy replacement...")
    pattern = r'const\s+response\s*=\s*await\s+fetch\("http://127\.0\.0\.1:8000/api/render/v1/single-frame",\s*\{\s*method:\s*"POST",\s*headers:\s*\{"Content-Type":\s*"application/json"\},\s*body:\s*JSON\.stringify\(\{\s*target_id:\s*ast\.id,\s*prompt:\s*newPrompt,\s*seed:\s*state\.seed,\s*style_lock:\s*true\s*\}\)\s*\}\);\s*const\s+res\s*=\s*await\s+response\.json\(\);'
    html, count = re.subn(pattern, new_rebuild_asset, html, flags=re.DOTALL)
    print(f"Fuzzy rebuildAssetCard replaced: {count} occurrences")
else:
    html = html.replace(old_rebuild_asset, new_rebuild_asset)
    print("Exact rebuildAssetCard replaced.")

# PATCH 6 - handleD1Next
old_d1_next = """        const response = await fetch("http://127.0.0.1:8000/api/story/v1/generate-storyboard", {
          method: "POST"
        });
        const res = await response.json();"""

new_d1_next = """        const res = await pywebview.api.generate_storyboard();"""

if old_d1_next not in html:
    print("WARNING: Exact old_d1_next not found, trying fuzzy replacement...")
    pattern = r'const\s+response\s*=\s*await\s+fetch\("http://127\.0\.0\.1:8000/api/story/v1/generate-storyboard",\s*\{\s*method:\s*"POST"\s*\}\);\s*const\s+res\s*=\s*await\s+response\.json\(\);'
    html, count = re.subn(pattern, new_d1_next, html, flags=re.DOTALL)
    print(f"Fuzzy handleD1Next replaced: {count} occurrences")
else:
    html = html.replace(old_d1_next, new_d1_next)
    print("Exact handleD1Next replaced.")

# PATCH 7 - rebuildFrameCard
old_rebuild_frame = """        const response = await fetch("http://127.0.0.1:8000/api/render/v1/single-frame", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            target_id: frame_id,
            prompt: newPrompt,
            seed: state.seed,
            style_lock: true
          })
        });
        const res = await response.json();"""

new_rebuild_frame = """        const res = await pywebview.api.render_single_frame({
            target_id: frame_id,
            prompt: newPrompt,
            seed: state.seed,
            style_lock: true
          });"""

if old_rebuild_frame not in html:
    print("WARNING: Exact old_rebuild_frame not found, trying fuzzy replacement...")
    pattern = r'const\s+response\s*=\s*await\s+fetch\("http://127\.0\.0\.1:8000/api/render/v1/single-frame",\s*\{\s*method:\s*"POST",\s*headers:\s*\{"Content-Type":\s*"application/json"\},\s*body:\s*JSON\.stringify\(\{\s*target_id:\s*frame_id,\s*prompt:\s*newPrompt,\s*seed:\s*state\.seed,\s*style_lock:\s*true\s*\}\)\s*\}\);\s*const\s+res\s*=\s*await\s+response\.json\(\);'
    html, count = re.subn(pattern, new_rebuild_frame, html, flags=re.DOTALL)
    print(f"Fuzzy rebuildFrameCard replaced: {count} occurrences")
else:
    html = html.replace(old_rebuild_frame, new_rebuild_frame)
    print("Exact rebuildFrameCard replaced.")

# PATCH 8 - handleSynthesize
old_synthesize = """        const response = await fetch("http://127.0.0.1:8000/api/story/v1/synthesize", {
          method: "POST"
        });
        const res = await response.json();"""

new_synthesize = """        const res = await pywebview.api.synthesize_video();"""

if old_synthesize not in html:
    print("WARNING: Exact old_synthesize not found, trying fuzzy replacement...")
    pattern = r'const\s+response\s*=\s*await\s+fetch\("http://127\.0\.0\.1:8000/api/story/v1/synthesize",\s*\{\s*method:\s*"POST"\s*\}\);\s*const\s+res\s*=\s*await\s+response\.json\(\);'
    html, count = re.subn(pattern, new_synthesize, html, flags=re.DOTALL)
    print(f"Fuzzy handleSynthesize replaced: {count} occurrences")
else:
    html = html.replace(old_synthesize, new_synthesize)
    print("Exact handleSynthesize replaced.")

# PATCH 9 & 10 - downloadEpicVideo fetches & browser fallback
old_download = """          // 2. 将此物理绝对路径发送给 API 中控进行安全复制
          const response = await fetch("http://127.0.0.1:8000/api/story/v1/download", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              source_file_relative_path: state.relativeVideoPath,
              target_absolute_path: savePath
            })
          });
          const res = await response.json();
          if (res.status === "success") {
            showCustomModal("🎉 保存成功！", `大导演，您的电影大作已成功下载并导出至：\\n\\n${savePath}`);
          } else {
            showCustomModal("⚠️ 保存失败", "文件物理拷贝失败，请核对写入权限后重试！");
          }
        } catch(e) {
          showCustomModal("⚠️ 对话框异常", "桌面系统接口交互异常，请重试！");
        }
      } else {
        // 兜底（以防是在普通浏览器里进行测试联调，而不是桌面 App 壳子中）
        window.open(`http://127.0.0.1:8000/static/runs/${state.relativeVideoPath}`, "_blank");
        showToast("🍿 已通过浏览器直接为您弹开视频下载！");
      }"""

new_download = """          // 2. 将此物理绝对路径发送给 API 中控进行安全复制
          const res = await pywebview.api.download_video({
              source_file_relative_path: state.relativeVideoPath,
              target_absolute_path: savePath
            });
          if (res.status === "success") {
            showCustomModal("🎉 保存成功！", `大导演，您的电影大作已成功下载并导出至：\\n\\n${savePath}`);
          } else {
            showCustomModal("⚠️ 保存失败", res.detail || "文件拷贝失败，请核对写入权限后重试！");
          }
        } catch(e) {
          showCustomModal("⚠️ 对话框异常", "桌面系统接口交互异常，请重试！");
        }
      } else {
        // 兜底（浏览器调试模式，无 pywebview 环境）
        showToast("⚠️ 请通过 启动调色板.bat 打开桌面 App 使用完整下载功能。");
      }"""

# Normalizing and doing exact match for download
if "http://127.0.0.1:8000/api/story/v1/download" in html:
    # Let's replace the whole try-catch and else block of download
    # We will do a replacement based on the lines we read
    # Lines 1656 to 1677:
    target_block = """          // 2. 将此物理绝对路径发送给 API 中控进行安全复制
          const response = await fetch("http://127.0.0.1:8000/api/story/v1/download", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              source_file_relative_path: state.relativeVideoPath,
              target_absolute_path: savePath
            })
          });
          const res = await response.json();
          if (res.status === "success") {
            showCustomModal("🎉 保存成功！", `大导演，您的电影大作已成功下载并导出至：\\n\\n${savePath}`);
          } else {
            showCustomModal("⚠️ 保存失败", "文件物理拷贝失败，请核对写入权限后重试！");
          }
        } catch(e) {
          showCustomModal("⚠️ 对话框异常", "桌面系统接口交互异常，请重试！");
        }
      } else {
        // 兜底（以防是在普通浏览器里进行测试联调，而不是桌面 App 壳子中）
        window.open(`http://127.0.0.1:8000/static/runs/${state.relativeVideoPath}`, "_blank");
        showToast("🍿 已通过浏览器直接为您弹开视频下载！");
      }"""
    
    # Let's adjust target block with single newlines
    target_block_single = target_block.replace("\\n\\n", "\\n\\n") # already single-slashed in html
    
    if target_block_single in html:
        html = html.replace(target_block_single, new_download)
        print("Exact download block replaced.")
    else:
        # Let's do a regex replace
        pattern = r'// 2\. 将此物理绝对路径发送给 API 中控进行安全复制.*?showToast\("🍿 已通过浏览器直接为您弹开视频下载！"\);\s*\}'
        html, count = re.subn(pattern, """// 2. 将此物理绝对路径发送给 API 中控进行安全复制
          const res = await pywebview.api.download_video({
              source_file_relative_path: state.relativeVideoPath,
              target_absolute_path: savePath
            });
          if (res.status === "success") {
            showCustomModal("🎉 保存成功！", `大导演，您的电影大作已成功下载并导出至：\\n\\n${savePath}`);
          } else {
            showCustomModal("⚠️ 保存失败", res.detail || "文件拷贝失败，请核对写入权限后重试！");
          }
        } catch(e) {
          showCustomModal("⚠️ 对话框异常", "桌面系统接口交互异常，请重试！");
        }
      } else {
        // 兜底（浏览器调试模式，无 pywebview 环境）
        showToast("⚠️ 请通过 启动调色板.bat 打开桌面 App 使用完整下载功能。");
      }""", html, flags=re.DOTALL)
        print(f"Fuzzy download replaced: {count} occurrences")

# PATCH 11 - handleApiError
old_api_error = """    // ── 🩺 容灾报错与重试拦截机制 ──
    function handleApiError(err, retryCallback) {
      console.error("[API ERROR] Catch-Guard:", err);
      
      // 抛出异常时，前端本地状态（输入文本、调好的 presets 参数等）绝对保留！
      // 弹出一个高质感对话框，提供“一键无缝重试”
      showCustomModal(
        "⚠️ 本地生图显卡/API 队列排队中",
        "由于本地大模型服务可能正在全力拼装或 GPU 生图显存较挤，出现响应超时。请点击下方一键重试，系统将原样重新发起刚才的工作流请求，无需刷新！",
        "💡 立即发起一键重试",
        true, // 显示取消按钮，留存状态
        retryCallback
      );
    }"""

new_api_error = """    // ── 🩺 容灾报错与重试拦截机制 ──
    function handleApiError(err, retryCallback) {
      console.error("[Bridge ERROR]:", err);
      
      // 抛出异常时，前端本地状态（输入文本、调好的 presets 参数等）绝对保留！
      // 弹出一个高质感对话框，提供“一键无缝重试”
      showCustomModal(
        "⚠️ 后台处理发生异常",
        `后台脚本执行中出现错误：${err && err.message ? err.message : '未知异常'}。请点击下方按钮重新发起请求（当前输入内容已全部保留）。`,
        "💡 立即重新发起请求",
        true, // 显示取消按钮，留存状态
        retryCallback
      );
    }"""

if old_api_error not in html:
    print("WARNING: Exact old_api_error not found, trying fuzzy replacement...")
    pattern = r'function\s+handleApiError\s*\(err,\s*retryCallback\)\s*\{.*?showCustomModal\(.*?"⚠️ 本地生图显卡/API 队列排队中".*?\);\s*\}'
    html, count = re.subn(pattern, new_api_error, html, flags=re.DOTALL)
    print(f"Fuzzy handleApiError replaced: {count} occurrences")
else:
    html = html.replace(old_api_error, new_api_error)
    print("Exact handleApiError replaced.")

html_path.write_text(html, encoding="utf-8")
print("SUCCESS: patch_all_bridge_fetches.py script ran completely!")
