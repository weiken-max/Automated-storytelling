// ── 🔌 连接状态灯 (v2.0 JS Bridge 版) ──
function checkApiConnection() {
  if (typeof pywebview !== 'undefined' && pywebview.api) {
    const badge = document.getElementById("connectionBadge");
    const light = document.getElementById("badgeLight");
    const txt = document.getElementById("badgeText");
    if (badge) badge.className = "flex items-center space-x-2 text-[10px] font-mono tracking-widest px-3 py-1.5 rounded bg-slate-900 border border-slate-800 text-emerald-400";
    if (light) light.className = "w-2 h-2 rounded-full bg-emerald-500 animate-pulse";
    if (txt) txt.innerText = "STATUS: LIVE (BRIDGE CONNECTED)";
  } else {
    const badge = document.getElementById("connectionBadge");
    const light = document.getElementById("badgeLight");
    const txt = document.getElementById("badgeText");
    if (badge) badge.className = "flex items-center space-x-2 text-[10px] font-mono tracking-widest px-3 py-1.5 rounded bg-slate-900 border border-slate-800 text-red-500";
    if (light) light.className = "w-2 h-2 rounded-full bg-red-500 animate-pulse";
    if (txt) txt.innerText = "STATUS: OFFLINE (BRIDGE NOT READY)";
  }
}

window.addEventListener('pywebviewready', function() { 
  checkApiConnection(); 
  detectRestorableSession();
  loadChannelsFromBackend();
});

setTimeout(checkApiConnection, 500);
setInterval(checkApiConnection, 5000);

function onBackendProgress(stage, percent, message) {
  console.log('[Bridge] ' + stage + ' ' + percent + '% - ' + message);
  var logEl = document.getElementById('assistantLogText');
  if (logEl && message) { logEl.innerText = message; }
}

// ── 📊 后台大盘实时审计面板逻辑 ──
let backstageInterval = null;

function toggleBackstageDrawer() {
  const drawer = document.getElementById("backstageDrawer");
  if (!drawer) return;
  drawer.classList.toggle("open");
  
  const isOpen = drawer.classList.contains("open");
  if (isOpen) {
    updateBackstageDrawer();
    if (!backstageInterval) {
      backstageInterval = setInterval(updateBackstageDrawer, 2000);
    }
  } else {
    if (backstageInterval) {
      clearInterval(backstageInterval);
      backstageInterval = null;
    }
  }
}

async function updateBackstageDrawer() {
  if (typeof pywebview === 'undefined' || !pywebview.api) return;
  try {
    const res = await pywebview.api.get_realtime_audit_logs();
    if (res.status === "success") {
      renderBackstageData(res.stages);
    }
  } catch (err) {
    console.error("Failed to fetch backstage audit logs:", err);
  }
}

// ── 🔄 历史会话检测与一键断点恢复逻辑 ──
let restorableSessionData = null;

async function detectRestorableSession() {
  if (typeof pywebview === 'undefined' || !pywebview.api) return;
  try {
    const res = await pywebview.api.get_restorable_session();
    if (res.status === "success" && res.run_id) {
      restorableSessionData = res;
      
      const rRunId = document.getElementById("restoreRunId");
      if (rRunId) rRunId.innerText = res.run_id;
      
      let cnStage = "C 剧本编写";
      if (res.stage === "D1") cnStage = "D1 定妆照展示";
      else if (res.stage === "E") cnStage = "E 分镜底片大网格";
      else if (res.stage === "F") cnStage = "F 最终多轨合并与电影放映室";
      
      const recStage = document.getElementById("restoreRecommendStage");
      if (recStage) recStage.innerText = cnStage;
      
      const sessionModal = document.getElementById("sessionRestoreModal");
      if (sessionModal) sessionModal.classList.remove("hidden");
    }
  } catch (err) {
    console.error("Failed to detect restorable session:", err);
  }
}

function restoreSession() {
  if (!restorableSessionData) return;
  const sessionModal = document.getElementById("sessionRestoreModal");
  if (sessionModal) sessionModal.classList.add("hidden");
  performSessionRecovery(restorableSessionData);
}
