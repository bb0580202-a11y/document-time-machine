"use strict";
// 前端:左版本树(SVG 分段轴/泳道/焦点折叠) + 右相册(卡片/三动作),树↔相册联动。
// 不写业务逻辑(还原/备注/里程碑/布局全在 engine via pywebview.api + treemap)。

let CURRENT_FOLDER = null;
let TREE = null;                 // 最近一次 get_treemap
let LANE_OF = {};                // full_id -> lane(给相册色条)
let FOCUS_LANE = 0;              // 当前完整展开的泳道
let LAST_FP = "";                // 版本指纹,轮询比对(变了才自动刷新)
let CARDS = [];                  // 最近一次 get_album(簇 toggle 时重渲相册,不重新拉数据)
let EXPANDED_CLUSTERS = new Set(); // 已展开的簇身份(clusterKey),跨重渲/轮询持久,仅切库重置
let JUST_EXPANDED = null;        // 本次 toggle 刚展开的簇 → 只它淡入,轮询重渲不闪
let LAST_FLASH = null, FLASH_T = null;  // 相册高亮:只留一张、连点不堆叠

const LANE_COLORS = ["#2563eb", "#f59e0b", "#16a34a", "#db2777", "#7c3aed", "#0891b2"];
const laneColor = (i) => LANE_COLORS[((i % LANE_COLORS.length) + LANE_COLORS.length) % LANE_COLORS.length];
// 簇身份:首+尾 full_id(比数组下标稳,跨重渲/轮询不串)
const clusterKey = (c) => c.node_ids[0] + ":" + c.node_ids[c.node_ids.length - 1];

// 分段轴布局常量
// 树为主视图后整体放大一档(初值,CP-1 真机微调);保可读优雅,不堆信息。
const FOCUS_X = 124, FOLD_X0 = 280, FOLD_W = 140;
const TOP_PAD = 22, NODE_GAP = 54, MIN_SEG_H = 34, BREAK_H = 50, AXIS_W = 7;

window.addEventListener("pywebviewready", init);

async function init() {
  try {
    document.getElementById("addFolderBtn").onclick = addFolderFlow;
    document.getElementById("openFolderBtn").onclick = () => {
      if (!CURRENT_FOLDER) return toast("先添加一个文件夹");
      pywebview.api.reveal_path(CURRENT_FOLDER).catch(showError);
    };
    document.getElementById("removeFolderBtn").onclick = removeCurrentFolder;
    document.getElementById("archiveBtn").onclick = archiveCurrentFolder;
    document.getElementById("resumeBtn").onclick = resumeCurrentFolder;
    document.getElementById("archivedBanner").addEventListener("click", (ev) => {
      if (ev.target.closest('[data-x="resume"]')) resumeCurrentFolder();
    });
    const sel = document.getElementById("folderSelect");
    sel.onchange = () => { loadFolder(sel.value); updateArchiveUI(); };
    document.getElementById("treeToggle").onclick = () =>
      document.getElementById("treePane").classList.toggle("collapsed");
    document.getElementById("refreshBtn").onclick = () => loadFolder(CURRENT_FOLDER);
    document.getElementById("album").addEventListener("click", onAlbumClick);
    await initAutostartToggle();
    initPaneResize();
    await refreshFolderSelect();
    checkDowntime();             // 开界面时回看一次:守护刚才停过吗
    startPolling();
  } catch (e) { showError(e); }
}

// 开机自动守护开关:起窗回显当前状态,切换调 bridge;失败回弹 + 人话
async function initAutostartToggle() {
  const chk = document.getElementById("autostartChk");
  chk.checked = await pywebview.api.get_autostart();
  chk.onchange = async () => {
    try {
      await pywebview.api.set_autostart(chk.checked);
      toast(chk.checked ? "已开启,下次开机自动在后台守护" : "已关闭开机自启");
    } catch (e) { chk.checked = !chk.checked; showError(e); }
  };
}

// 拖分隔条自定义树↔相册宽度比例;拖动即解除默认 42%/460px 约束,交给用户
function initPaneResize() {
  const main = document.querySelector("main");
  const tree = document.getElementById("treePane");
  const divider = document.getElementById("paneDivider");
  let dragging = false, startX = 0, startW = 0;
  divider.addEventListener("mousedown", (e) => {
    dragging = true; e.preventDefault();
    startX = e.clientX;
    startW = tree.getBoundingClientRect().width;   // 记下抓握那刻的实际宽度→相对移动,不跳
    tree.style.maxWidth = "none";
    tree.style.transition = "none";                // 拖拽时禁过渡,否则会"先动画归位再跟手"
    divider.classList.add("drag");
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const rect = main.getBoundingClientRect();
    const w = Math.max(160, Math.min(rect.width * 0.7, startW + (e.clientX - startX)));
    tree.style.width = w + "px";       // 相对起始宽度,精确跟手、零跳变
  });
  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    tree.style.transition = "";       // 恢复(拖拽时临时禁的)
    divider.classList.remove("drag");
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  });
}

// 通用确认弹窗(pywebview 的原生 confirm() 不可靠,自己做一个)
function confirmAction(message, onOk) {
  const m = document.getElementById("modal");
  m.querySelector(".modal-msg").textContent = message;
  m.hidden = false;
  m.onclick = (ev) => {
    if (ev.target === m) { m.hidden = true; m.onclick = null; return; }  // 点遮罩空白关
    const b = ev.target.closest("button");
    if (!b) return;
    m.hidden = true; m.onclick = null;
    if (b.dataset.x === "ok") onOk();
  };
}

// 移除当前库:出列表、停止守护;文件和历史都留在磁盘(INV-1),可重新添加找回
function removeCurrentFolder() {
  const sel = document.getElementById("folderSelect");
  const opt = sel.selectedOptions[0];
  if (!opt || !opt.dataset.uuid) return toast("没有可移除的文件夹");
  const name = opt.textContent;
  const path = opt.value;            // 撤销要用路径重新添加
  confirmAction(
    "确定不再看管「" + name + "」吗？\n\n" +
    "· 你的文件夹、文件、全部历史版本都留在原处，一个都不删\n" +
    "· 只是时光机停止自动备份它\n" +
    "· 以后随时可以重新添加，历史照样找回\n\n" +
    "（这一步是安全、可撤销的——不会丢任何东西。）",
    async () => {
      try {
        await pywebview.api.remove_folder(opt.dataset.uuid);
        await refreshFolderSelect();
        showUndoRemove(name, path);    // 让"可逆"看得见点得到:一键撤销
      } catch (e) { showError(e); }
    }
  );
}

// 移除后的一键撤销(可逆不只是嘴上说):点撤销=按原路径重新添加,历史经 UUID 找回
function showUndoRemove(name, path) {
  const box = document.getElementById("restoreResult");
  box.innerHTML =
    `<span class="msg">已移除「${esc(name)}」（文件和历史都还在）</span>` +
    `<button class="btn small primary" data-x="undo">撤销</button>` +
    `<button class="btn small ghost" data-x="close">知道了</button>`;
  box.hidden = false;
  box.onclick = async (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    box.hidden = true;
    if (b.dataset.x === "undo") {
      try {
        const e = await pywebview.api.add_folder(path);
        await refreshFolderSelect(e.path);
        toast("已恢复：" + name);
      } catch (err) { showError(err); }
    }
  };
}

async function addFolderFlow() {
  let picked;
  try {
    picked = await pywebview.api.pick_folder();
  } catch (e) { return showError(e); }
  if (!picked) return;                       // 用户取消
  toast("正在开启守护…");
  try {
    const entry = await pywebview.api.add_folder(picked);
    // 加完本地刷新即生效(不依赖守护):重填下拉 + 选中新加的 + 载入
    await refreshFolderSelect(entry.path);
    toast("已开始守护：" + entry.name);
  } catch (e) { showError(e); }
}

// 重填文件夹下拉,可选 selectPath 指定选中项;无 active 时显示空状态大按钮
let FOLDERS = [];                 // 最近一次 list_folders,给归档 UI 查当前库的 archived
async function refreshFolderSelect(selectPath) {
  const folders = await pywebview.api.list_folders();
  FOLDERS = folders;
  const watched = folders.filter((f) => f.status === "active" && !f.archived);
  const archived = folders.filter((f) => f.status === "active" && f.archived);
  const sel = document.getElementById("folderSelect");
  sel.innerHTML = "";
  if (!watched.length && !archived.length) {
    sel.hidden = true;                                     // 没库时藏下拉(空 select 就是那个"半截框")
    document.getElementById("docName").textContent = "";   // 没库时不显示文档名
    document.getElementById("healthWarn").hidden = true;   // 没库了,清掉可能残留的红条
    document.getElementById("treeSvg").innerHTML = "";     // 移除最后一个库后清空树(否则旧树残留)
    const _hint = document.getElementById("treeHint"); if (_hint) _hint.textContent = "";
    CURRENT_FOLDER = null;
    updateArchiveUI();
    document.getElementById("album").innerHTML =
      '<p class="empty">还没有被守护的文件夹。' +
      '<button id="emptyAddBtn" class="btn">＋ 添加要守护的文件夹</button></p>';
    document.getElementById("emptyAddBtn").onclick = addFolderFlow;
    return;
  }
  sel.hidden = false;                    // 有库→显示下拉
  const mkOpt = (f, prefix) => {
    const o = document.createElement("option");
    o.value = f.path; o.textContent = prefix + f.name;
    o.dataset.uuid = f.uuid;             // 归档/移除用 uuid(身份证,不认路径)
    return o;
  };
  const addGroup = (label, list, prefix) => {
    if (!list.length) return;
    const g = document.createElement("optgroup"); g.label = label;
    list.forEach((f) => g.appendChild(mkOpt(f, prefix)));
    sel.appendChild(g);                  // 「看管中」「已归档」分组,native 沉底分开排
  };
  addGroup("看管中", watched, "");
  addGroup("已归档", archived, "已归档 · ");
  const all = [...watched, ...archived];
  const target = (selectPath && all.some((f) => f.path === selectPath))
    ? selectPath : all[0].path;
  sel.value = target;
  loadFolder(target);
  updateArchiveUI();
}

// 当前选中库的 archived → 切归档/继续记录按钮、持久横幅、界面冻结态(强对比)
function currentFolderObj() {
  const sel = document.getElementById("folderSelect");
  return FOLDERS.find((f) => f.path === sel.value) || null;
}
function updateArchiveUI() {
  const f = currentFolderObj();
  const archived = !!(f && f.archived);
  document.getElementById("archiveBtn").hidden = archived;
  document.getElementById("resumeBtn").hidden = !archived;
  document.getElementById("archivedBanner").hidden = !archived;
  document.querySelector("main").classList.toggle("archived-view", archived);
}

function archiveCurrentFolder() {
  const opt = document.getElementById("folderSelect").selectedOptions[0];
  if (!opt || !opt.dataset.uuid) return toast("没有可归档的文件夹");
  const name = (currentFolderObj() || {}).name || opt.textContent;
  confirmAction(
    "归档「" + name + "」？\n\n" +
    "· 会停止记录新版本（不再自动备份）\n" +
    "· 已有的全部历史版本都保留，随时可以翻、可以还原\n" +
    "· 它留在列表的「已归档」里，随时点『继续记录』恢复\n\n" +
    "（安全、可逆——不会丢任何东西。）",
    async () => {
      try {
        await pywebview.api.archive_folder(opt.dataset.uuid);
        await refreshFolderSelect(opt.value);     // 保持选中它 → 看冻结态
        toast("已归档：" + name);
      } catch (e) { showError(e); }
    }
  );
}

async function resumeCurrentFolder() {
  const opt = document.getElementById("folderSelect").selectedOptions[0];
  if (!opt || !opt.dataset.uuid) return toast("没有可继续记录的文件夹");
  const name = (currentFolderObj() || {}).name || opt.textContent;
  try {
    await pywebview.api.resume_folder(opt.dataset.uuid);   // 先补拍基线再恢复看管
    await refreshFolderSelect(opt.value);
    toast("已继续记录：" + name + "（已补记一版当前状态）");
  } catch (e) { showError(e); }
}

// 裸奔回看:守护刚才没打招呼就停过(已恢复)→ 黄条告诉用户"那段没保护",点知道了清掉
async function checkDowntime() {
  try {
    const d = await pywebview.api.check_downtime();
    if (!d || !d.gap_seconds) return;
    const el = document.getElementById("downtimeWarn");
    el.innerHTML =
      `<span class="msg">⏸ 时光机刚才约 ${humanizeDur(d.gap_seconds)} 没在守护（已恢复）` +
      `，这期间对文件的改动可能没存进去，建议检查一下那几个文件。</span>` +
      `<button class="btn small" data-x="ok">知道了</button>`;
    el.hidden = false;
    el.onclick = (ev) => {
      if (!ev.target.closest("button")) return;
      el.hidden = true;
      pywebview.api.ack_downtime().catch(() => {});
    };
  } catch (e) { /* 回看失败不挡用 */ }
}

function humanizeDur(s) {
  if (s >= 3600) return Math.round(s / 3600) + " 小时";
  return Math.max(1, Math.round(s / 60)) + " 分钟";
}

// 顶栏「文档时光机」下显示当前守护的文档名:取最新版本的主文档名,回落库文件夹名
function updateDocName(cards) {
  const primary = (cards.length && cards[0].files && cards[0].files.length)
    ? cards[0].files[0].name
    : (CURRENT_FOLDER ? CURRENT_FOLDER.split(/[\\/]/).pop() : "");
  document.getElementById("docName").textContent = primary;
}

// 仓库自检红横幅:坏了亮、好了隐(随状态自动显隐,不让小白以为还被完整保护)
function updateHealthWarn(health) {
  const el = document.getElementById("healthWarn");
  if (health && health.ok === false) {
    el.textContent = "⚠️ " + (health.reason || "这个文件夹的版本历史可能有一处损坏。");
    el.hidden = false;
  } else {
    el.hidden = true;
  }
}

const fpKey = (head, count) => count + ":" + head;

async function pollRefresh() {
  if (!CURRENT_FOLDER) return;
  if (document.hidden) return;       // 窗口最小化/在后台→不轮询(Windows 上每次 peek 都 spawn git ~900ms,白烧)
  if (document.querySelector(".inline-input")) return;   // 有备注/确认框开着→不打断
  try {
    const fp = await pywebview.api.peek(CURRENT_FOLDER);
    if (fpKey(fp.head, fp.count) !== LAST_FP) loadFolder(CURRENT_FOLDER);
  } catch (e) { /* 轮询静默,不打扰 */ }
}

function startPolling() {
  // Windows 上每次 peek 要 spawn git(~900ms,Defender 扫未签名 git.exe),别频繁轮询:
  // 30s 一次够及时;窗口重新可见时立刻刷一次(看 dtm 那刻是最新的),后台时完全不轮询。
  setInterval(pollRefresh, 30000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) pollRefresh(); });
}

async function loadFolder(folder) {
  const switched = folder !== CURRENT_FOLDER;   // 切库才重设树折叠默认;同库刷新尊重用户手动开关
  CURRENT_FOLDER = folder;
  // 自检(3 次 git)只在切库时跑——同库刷新/30s 轮询不重查,省 git(Windows 上每次~900ms)。
  // 并行不阻塞主内容;坏仓时独立把红条亮出来。
  if (switched) pywebview.api.check_health(folder).then(updateHealthWarn).catch(() => {});
  try {
    const [tm, cards] = await Promise.all([
      pywebview.api.get_treemap(folder),
      pywebview.api.get_album(folder),
    ]);
    TREE = tm;
    CARDS = cards;
    LANE_OF = {};
    tm.nodes.forEach((n) => (LANE_OF[n.full_id] = n.lane));
    const cur = tm.nodes.find((n) => n.is_current);
    FOCUS_LANE = cur ? cur.lane : (tm.lanes[0] ? tm.lanes[0].index : 0);
    // 默认显示版本树(用户要求:打开先看树);仅在切库时设,之后尊重手动开关——
    // 否则 4s 轮询/还原触发的 loadFolder 会把用户的折叠选择改掉。
    if (switched) {
      document.getElementById("treePane").classList.remove("collapsed");
      EXPANDED_CLUSTERS.clear();   // 切库才重置展开态;同库刷新/轮询保留(否则展开会被刷没)
    }
    document.getElementById("treeHint").textContent =
      tm.lanes.length <= 1 ? "" : "（点细灰条切到另一条线）";
    renderTree(tm);
    renderAlbum(cards);
    updateDocName(cards);
    LAST_FP = fpKey(cur ? cur.full_id : "", tm.nodes.length);   // 记录指纹供轮询比对
  } catch (e) {
    // 多半是坏仓(get_album 读 log 抛):给相册一句人话;红条由并行的 check_health 独立负责
    document.getElementById("album").innerHTML =
      '<p class="empty">这个文件夹的历史暂时读不出来。若顶部有红色提示，说明它可能损坏了。</p>';
  }
}

// ==================== 版本树(SVG 分段轴) ====================
const SVGNS = "http://www.w3.org/2000/svg";
function svg(tag, attrs, text) {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (text != null) e.textContent = text;
  return e;
}
const tms = (iso) => new Date(iso).getTime() / 1000;   // iso -> 秒(节点带时区/刻度本地,本机一致)

function label(parent, x, y, text, fill, weight, size) {
  parent.appendChild(svg("text", { x, y, "font-size": size || 12, fill, "font-weight": weight || 400 }, text));
}

// 地标容器:hover 围绕(cx,cy)放大加粗,点击联动到相册
function makeLandmark(el, cx, cy, fullId) {
  const g = svg("g", { class: "lm" });
  g.style.cursor = "pointer";
  g.addEventListener("mouseenter", () =>
    g.setAttribute("transform", `translate(${cx} ${cy}) scale(1.18) translate(${-cx} ${-cy})`));
  g.addEventListener("mouseleave", () => g.removeAttribute("transform"));
  if (fullId) g.addEventListener("click", (e) => { e.stopPropagation(); focusAlbumCard(fullId); });
  el.appendChild(g);
  return g;
}

function renderTree(tm) {
  const el = document.getElementById("treeSvg");
  el.innerHTML = "";
  const byId = {};
  tm.nodes.forEach((n) => (byId[n.full_id] = n));
  const focus = FOCUS_LANE;

  // 焦点泳道的渲染项:普通节点 + 簇。簇分两态——
  //   未展开 → 画「⋯N个存档」摘要(成员不单独画);已展开 → 成员当普通节点画 + 顶上加「收起」头。
  const allClusters = tm.clusters.filter((c) => c.lane === focus);
  const memberKey = {};            // full_id -> clusterKey(仅已展开的簇,用于淡入判定)
  const folded = [];
  allClusters.forEach((c) => {
    const k = clusterKey(c);
    if (EXPANDED_CLUSTERS.has(k)) c.node_ids.forEach((id) => (memberKey[id] = k));
    else folded.push(c);
  });
  const clustered = new Set();     // 仍被折起来的成员(不单独画)
  folded.forEach((c) => c.node_ids.forEach((id) => clustered.add(id)));
  const items = [];
  tm.nodes.filter((n) => n.lane === focus && !clustered.has(n.full_id))
    .forEach((n) => items.push({ type: "node", t: tms(n.iso_time), id: n.full_id, node: n,
                                 fromFold: memberKey[n.full_id] != null,   // 来自(已展开的)折叠簇 → 换色
                                 fade: memberKey[n.full_id] != null && memberKey[n.full_id] === JUST_EXPANDED }));
  folded.forEach((c) =>
    items.push({ type: "cluster", t: (tms(c.start_iso) + tms(c.end_iso)) / 2, id: "cl-" + c.node_ids[0], cluster: c }));
  allClusters.forEach((c) => {     // 已展开的簇:在成员顶端插一个「收起」头(t 比首成员略早→排在其上)
    if (EXPANDED_CLUSTERS.has(clusterKey(c)))
      items.push({ type: "collapse", t: tms(c.start_iso) - 1, id: "cx-" + c.node_ids[0], cluster: c,
                   fade: clusterKey(c) === JUST_EXPANDED });
  });
  items.sort((a, b) => a.t - b.t);

  // 按 gap 切段(gap.after_id 之后断开)
  const gapDays = {};
  tm.gaps.forEach((g) => (gapDays[g.after_id] = g.days));
  const segs = [];
  let cur = [];
  items.forEach((it) => {
    cur.push(it);
    if (it.type === "node" && gapDays[it.id] != null) {
      segs.push({ items: cur, gapDays: gapDays[it.id] });
      cur = [];
    }
  });
  if (cur.length) segs.push({ items: cur, gapDays: 0 });

  // 段内节点等距排列(可读不重叠);刻度按相邻节点时间插值定位 → gap 两端仍对齐(CP-2)
  let y = TOP_PAD;
  segs.forEach((s, si) => {
    s.items.forEach((it, i) => (it.yAbs = y + i * NODE_GAP));
    s.tStart = s.items[0].t;
    s.tEnd = s.items[s.items.length - 1].t;
    s.top = y;
    s.h = Math.max(MIN_SEG_H, (s.items.length - 1) * NODE_GAP);
    y = s.top + s.h;
    if (si < segs.length - 1) { s.breakTop = y + 6; y += BREAK_H; }
  });
  const totalH = y + TOP_PAD;
  const W = Math.max(360, FOLD_X0 + Math.max(0, tm.lanes.length - 1) * FOLD_W + 96);

  const tToY = (t) => {
    for (const s of segs) {
      if (t < s.tStart || t > s.tEnd) continue;
      const its = s.items;
      if (its.length === 1) return its[0].yAbs;
      for (let i = 0; i < its.length - 1; i++) {
        const a = its[i], b = its[i + 1];
        if (t >= a.t && t <= b.t) {
          const f = b.t === a.t ? 0 : (t - a.t) / (b.t - a.t);
          return a.yAbs + f * (b.yAbs - a.yAbs);
        }
      }
      return its[its.length - 1].yAbs;
    }
    return null;   // 落在被压缩的空白里 → 不画
  };

  el.setAttribute("viewBox", `0 0 ${W} ${totalH}`);
  el.setAttribute("width", W);
  el.style.height = totalH + "px";

  // 时间标尺(跳过落在 gap 空白里的刻度)
  tm.ticks.forEach((tk) => {
    const ty = tToY(tms(tk.iso));
    if (ty == null) return;
    el.appendChild(svg("line", { x1: 66, y1: ty, x2: W - 10, y2: ty, stroke: "#e5e7eb", "stroke-dasharray": "2 5" }));
    label(el, 6, ty + 3, tk.label, "#b0b4ba", 400, 10);
  });

  // 始末标识:不论时间跨度多大,永远标出最早/最新版本的时间——数据挤在一起、标尺无刻度时也不空白(CP-1 反馈)
  if (items.length) {
    const isoOf = (it, end) => it.type === "node" ? it.node.iso_time : (end ? it.cluster.end_iso : it.cluster.start_iso);
    const fmt = (iso) => iso.slice(5, 16).replace("T", " ");   // 06-04 14:30
    const a = items[0], z = items[items.length - 1];
    label(el, 4, a.yAbs - 8, "最早 " + fmt(isoOf(a, false)), "#9ca3af", 600, 9.5);
    label(el, 4, z.yAbs + 16, "最新 " + fmt(isoOf(z, true)), "#9ca3af", 600, 9.5);
  }

  // 断裂带(空白压缩)
  segs.forEach((s) => { if (s.breakTop != null) drawBreak(el, s.breakTop, s.gapDays); });

  // 焦点泳道竖轴(逐段画,断裂处自然不连)
  const col = laneColor(focus);
  segs.forEach((s) =>
    el.appendChild(svg("line", { x1: FOCUS_X, y1: s.top, x2: FOCUS_X, y2: s.top + s.h, stroke: col, "stroke-width": AXIS_W, "stroke-linecap": "round" })));

  // 折叠泳道(其余 lane):细灰条 + 自描述 + 点击切焦点;并画跨泳道岔线
  let fx = FOLD_X0;
  tm.lanes.forEach((l) => {
    if (l.index === focus) return;
    drawFoldedLane(el, l, fx, tm, byId, focus, tToY);
    fx += FOLD_W;
  });

  // 焦点泳道地标 + 簇 + 收起头(等距 y)
  items.forEach((it) => {
    if (it.type === "cluster") drawCluster(el, it.cluster, FOCUS_X, it.yAbs);
    else if (it.type === "collapse") drawCollapse(el, it.cluster, FOCUS_X, it.yAbs, it.fade);
    else drawNode(el, it.node, FOCUS_X, it.yAbs, col, it.fade, it.fromFold);
  });

  // 树整体水平居中:按真实内容包围盒裁宽,配合 #treeBody 的 text-align:center 让树居中不贴左。
  // 焦点轴位置固定(FOCUS_X),切主干/支线轴不移动,故无需补间动画(bb 提的"丝滑"在此不适用)。
  let cw = W;
  try {
    const bb = el.getBBox();
    const pad = 22;
    cw = Math.ceil(bb.width + pad * 2);
    el.setAttribute("viewBox", `${Math.floor(bb.x - pad)} 0 ${cw} ${totalH}`);
  } catch (e) { /* 空内容时 getBBox 可能抛,退回原 W */ }
  el.setAttribute("width", cw);
  el.style.height = totalH + "px";
}

function drawNode(el, n, x, y, col, fade, fromFold) {
  const g = makeLandmark(el, x, y, n.full_id);
  if (fade) g.setAttribute("class", "lm just-expanded");   // 刚从簇里展开 → 淡入
  if (fromFold) col = "#8b5cf6";   // 来自折叠簇的成员:换靛紫,和普通节点(蓝)区分,呼应折叠主题
  const isMile = n.milestones.length > 0;
  if (n.is_current) {
    g.appendChild(svg("circle", { cx: x, cy: y, r: 9, fill: col }));
    g.appendChild(svg("text", { x, y: y - 13, "font-size": 14, "text-anchor": "middle" }, "📍"));
    label(g, x + 18, y - 1, "你在这里", "#1d4ed8", 700, 13.5);
    if (n.note) label(g, x + 18, y + 14, n.note, "#1f2937", 400, 12);
  } else if (isMile) {
    g.appendChild(svg("circle", { cx: x, cy: y, r: 10, fill: "#fde68a", stroke: "#d97706", "stroke-width": 3 }));
    label(g, x + 18, y - 2, "★ " + n.milestones[0], "#92400e", 700, 13.5);
    label(g, x + 18, y + 13, n.title, "#111827", 800, 13);
  } else if (n.note) {
    g.appendChild(svg("circle", { cx: x, cy: y, r: 7.5, fill: "#dbeafe", stroke: col, "stroke-width": 3 }));
    label(g, x + 18, y + 4, n.note, "#1f2937", 400, 13);
  } else {
    g.appendChild(svg("circle", { cx: x, cy: y, r: 6.5, fill: fromFold ? "#ede9fe" : "#fff", stroke: col, "stroke-width": 2.5 }));
  }
  if (n.is_branch_point) {
    const dy = n.is_current || isMile || n.note ? -14 : 4;
    // 放主干左侧(岔路向右,放对面不压岔出线),右对齐、加大
    g.appendChild(svg("text", { x: x - 16, y: y + dy, "font-size": 12, fill: "#4b5563",
                                "font-weight": 600, "text-anchor": "end" }, "⋔ 从这里岔出"));
  }
}

function drawCluster(el, c, x, y) {
  const g = makeLandmark(el, x, y, null);   // 不接 focusAlbumCard,改接 toggle 展开
  g.appendChild(svg("rect", { x: x - 18, y: y - 14, width: 180, height: 40, fill: "transparent" }));  // 大命中区:SVG 缝隙也可点
  g.appendChild(svg("line", { x1: x - 9, y1: y - 9, x2: x + 9, y2: y - 9, stroke: "#bfdbfe", "stroke-width": 2 }));
  g.appendChild(svg("line", { x1: x - 11, y1: y - 6, x2: x + 11, y2: y - 6, stroke: "#93c5fd", "stroke-width": 2 }));
  g.appendChild(svg("rect", { x: x - 15, y: y - 2, width: 30, height: 22, rx: 6, fill: "#eef2ff", stroke: "#2563eb", "stroke-width": 2 }));
  label(g, x + 24, y + 6, "⋯ " + c.count + " 个存档", "#1f2937", 600, 13);
  label(g, x + 24, y + 20, c.start_iso.slice(11, 16) + "–" + c.end_iso.slice(11, 16) + " · 点开", "#9ca3af", 400, 11);
  g.addEventListener("click", (e) => { e.stopPropagation(); toggleCluster(clusterKey(c)); });
}

// 已展开簇顶端的「收起」头:成员节点各自点击是定位相册,收起需独立入口
function drawCollapse(el, c, x, y, fade) {
  const g = svg("g", { class: "collapse-ctl" + (fade ? " just-expanded" : "") });
  g.style.cursor = "pointer";
  const x0 = x - 16, w = 172, cy = y + 1;
  // 实心紫色按钮 + 白字加粗:比节点更显眼(bb 反馈),且呼应折叠段的靛紫主题
  g.appendChild(svg("rect", { x: x0, y: y - 11, width: w, height: 24, rx: 8, fill: "#8b5cf6" }));
  g.appendChild(svg("text", { x: x0 + 12, y: y + 5, "font-size": 12.5, "font-weight": 700, fill: "#fff" }, "▾ 收起这 " + c.count + " 个存档"));
  // 悬停围绕按钮中心放大(和节点一致的手感)
  const cx = x0 + w / 2;
  g.addEventListener("mouseenter", () => g.setAttribute("transform", `translate(${cx} ${cy}) scale(1.1) translate(${-cx} ${-cy})`));
  g.addEventListener("mouseleave", () => g.removeAttribute("transform"));
  g.addEventListener("click", (e) => { e.stopPropagation(); toggleCluster(clusterKey(c)); });
  el.appendChild(g);
}

// 点簇/收起头/(T3后)相册 fold-head 都走这里:翻转展开态 → 重渲树+相册(同一份 EXPANDED_CLUSTERS)
function toggleCluster(key) {
  const expanding = !EXPANDED_CLUSTERS.has(key);
  if (expanding) EXPANDED_CLUSTERS.add(key);
  else EXPANDED_CLUSTERS.delete(key);
  JUST_EXPANDED = expanding ? key : null;   // 只本次展开的簇淡入
  renderTree(TREE);
  renderAlbum(CARDS);                        // 相册据同一份 EXPANDED_CLUSTERS 同步折叠
  JUST_EXPANDED = null;                      // 复位:后续轮询重渲不再闪
  if (expanding) {                           // 点树簇 → 相册滚到对应段(从相册头点则本就可见,无害)
    const fold = document.getElementById("fold-" + key);
    if (fold) fold.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function drawBreak(el, by, days) {
  const x = FOCUS_X;
  for (const off of [0, 12]) {
    el.appendChild(svg("path", { d: `M${x - 5} ${by + 7 + off} l9 -7 l-9 -7`, fill: "none", stroke: "#9ca3af", "stroke-width": 2 }));
  }
  label(el, x + 18, by + 13, "≈ 无改动 " + days + " 天(已压缩)", "#9ca3af", 400, 12);
}

function drawFoldedLane(el, lane, fx, tm, byId, focus, tToY) {
  const lnodes = tm.nodes.filter((n) => n.lane === lane.index);
  if (!lnodes.length) return;
  // 锚点:从焦点泳道岔出的那个父节点的 y(固定),折叠列自身固定排版,不随主线插值挤
  let bpY = null;
  for (const n of lnodes) {
    for (const pid of n.parents) {
      const p = byId[pid];
      if (p && p.lane === focus) { const py = tToY(tms(p.iso_time)); if (py != null) { bpY = py; break; } }
    }
    if (bpY != null) break;
  }
  if (bpY == null) {
    const ys = lnodes.map((n) => tToY(tms(n.iso_time))).filter((v) => v != null);
    bpY = ys.length ? Math.min(...ys) : TOP_PAD;
  }
  const tipY = bpY + 50;
  // 岔出曲线:焦点泳道分叉点 → 折叠列 tip
  el.appendChild(svg("path", { d: `M${FOCUS_X} ${bpY} C ${(FOCUS_X + fx) / 2} ${bpY}, ${fx} ${bpY}, ${fx} ${tipY}`, fill: "none", stroke: laneColor(lane.index), "stroke-width": 2.5, opacity: 0.5 }));
  // 入口标签(点切焦点展开整条)
  const g = svg("g", { class: "collapse-ctl" });   // 复用 .collapse-ctl 的 transform 过渡
  g.style.cursor = "pointer";
  label(g, fx + 5, bpY - 1, "▸ " + lane.name + " · " + (lane.summary.split(" · ")[1] || ""), laneColor(lane.index), 700, 12.5);
  label(g, fx + 5, bpY + 14, "点开看全部", "#6b7280", 600, 11);
  const hx = fx + 45, hy = bpY + 6;   // 悬停围绕入口中心放大
  g.addEventListener("mouseenter", () => g.setAttribute("transform", `translate(${hx} ${hy}) scale(1.1) translate(${-hx} ${-hy})`));
  g.addEventListener("mouseleave", () => g.removeAttribute("transform"));
  g.addEventListener("click", () => { FOCUS_LANE = lane.index; renderTree(TREE); });
  el.appendChild(g);
  // 只露最新一版(tip)
  const tip = lnodes.reduce((a, b) => (tms(b.iso_time) > tms(a.iso_time) ? b : a));
  drawFoldedTip(el, tip, fx, tipY, lane.index);
}

function drawFoldedTip(el, n, x, y, laneIdx) {
  const g = makeLandmark(el, x, y, n.full_id);
  const col = laneColor(laneIdx);
  if (n.milestones.length) {
    g.appendChild(svg("circle", { cx: x, cy: y, r: 8, fill: "#fde68a", stroke: "#d97706", "stroke-width": 2.5 }));
    label(g, x + 14, y + 4, "★ " + n.milestones[0] + "（最新）", "#b45309", 700, 12);
  } else if (n.note) {
    g.appendChild(svg("circle", { cx: x, cy: y, r: 6.5, fill: "#fff", stroke: col, "stroke-width": 2.5 }));
    label(g, x + 14, y + 4, n.note + "（最新）", "#6b7280", 500, 12);
  } else {
    g.appendChild(svg("circle", { cx: x, cy: y, r: 6, fill: "#fff", stroke: col, "stroke-width": 2.5 }));
    label(g, x + 14, y + 4, n.title + "（最新）", "#6b7280", 500, 12);
  }
}

function focusAlbumCard(fullId) {
  const card = document.getElementById("card-" + fullId);
  if (!card) return;
  // 只在卡片不在可视区时才平滑滚动:连点近邻卡不再反复触发滚动动画,去掉"粘滞"
  const pane = document.getElementById("albumPane");
  if (pane) {
    const cr = card.getBoundingClientRect(), pr = pane.getBoundingClientRect();
    if (cr.top < pr.top + 4 || cr.bottom > pr.bottom - 4)
      card.scrollIntoView({ behavior: "smooth", block: "center" });
  } else {
    card.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  // 高亮只留一张、清掉上次定时器,连点不堆叠
  if (LAST_FLASH && LAST_FLASH !== card) LAST_FLASH.classList.remove("flash");
  clearTimeout(FLASH_T);
  card.classList.add("flash");
  LAST_FLASH = card;
  FLASH_T = setTimeout(() => card.classList.remove("flash"), 1500);
}

// ==================== 相册 ====================
function renderAlbum(cards) {
  const root = document.getElementById("album");
  root.innerHTML = "";
  if (!cards.length) { root.innerHTML = '<p class="empty">还没有任何版本。</p>'; return; }
  // 簇成员就地折成 .fold 块(与树的簇一一对应、共用 EXPANDED_CLUSTERS 展开态)
  const cardCluster = {};
  ((TREE && TREE.clusters) || []).forEach((c) => c.node_ids.forEach((id) => (cardCluster[id] = c)));
  const cardById = {};
  cards.forEach((c) => (cardById[c.full_id] = c));
  const ordered = cards.slice().reverse();  // 相册统一成「最早在顶→最新在底」,与树同向
  const seen = new Set();
  for (const c of ordered) {
    const cl = cardCluster[c.full_id];
    if (cl) {
      const key = clusterKey(cl);
      if (seen.has(key)) continue;         // 该簇块已输出 → 跳过其余成员
      seen.add(key);
      root.appendChild(renderFold(cl, cardById));
    } else {
      root.appendChild(renderCard(c));
    }
  }
}

// 相册里的折叠段:头部可点(与树簇同步展/收),展开时露出成员卡 + 靛紫高亮区隔
function renderFold(cl, cardById) {
  const key = clusterKey(cl);
  const open = EXPANDED_CLUSTERS.has(key);
  const el = document.createElement("div");
  el.className = "fold" + (open ? " open active" : "");
  el.id = "fold-" + key;
  const span = cl.start_iso.slice(5, 16).replace("T", " ") + "–" + cl.end_iso.slice(11, 16);
  el.innerHTML =
    `<div class="fold-head"><span class="chev">▸</span>` +
    `<span>⋯ ${cl.count} 个存档 · ${esc(span)}</span></div>` +
    `<div class="fold-body"></div>`;
  const body = el.querySelector(".fold-body");
  cl.node_ids                                // 时间升序=最早在前,与相册(最早→最新)同向
    .forEach((id) => { if (cardById[id]) body.appendChild(renderCard(cardById[id])); });
  el.querySelector(".fold-head").addEventListener("click", () => toggleCluster(key));
  return el;
}

function renderCard(c) {
  const el = document.createElement("div");
  el.className = "card" + (c.is_current ? " current" : "");
  el.id = "card-" + c.full_id;
  el.dataset.id = c.full_id;

  const laneIdx = LANE_OF[c.full_id] != null ? LANE_OF[c.full_id] : 0;
  const title = c.note || c.abs_minute;
  const sub = c.note
    ? `<span class="abs">${esc(c.abs_minute)}</span><span class="rel"> · ${esc(c.relative)}</span>`
    : `<span class="rel">${esc(c.relative)}</span>`;
  const milestones = (c.milestones || []).map((m) =>
    `<span class="badge">★ ${esc(m)}<button class="badge-x" data-act="del-tag" data-tag="${esc(m)}" title="删除这个里程碑(版本不受影响)">×</button></span>`).join("");
  const here = c.is_current ? '<span class="here">📍 你在这里</span>' : "";
  const delNoteBtn = c.note
    ? '<button class="btn ghost" data-act="del-note" title="删除备注(版本不受影响)">删备注</button>'
    : "";
  const filesHtml = (c.files || [])
    .map((f) => `<div class="file-row"><span class="fname">${esc(f.name)} ${arrow(f.delta_sign)}</span></div>`)
    .join("");

  el.innerHTML = `
    <span class="lane-bar" style="background:${laneColor(laneIdx)}"></span>
    <div class="card-top">
      ${fileIcon((c.files[0] && c.files[0].name) || "")}
      <div class="card-main">
        <div class="title" title="完整时间 ${esc(c.abs_seconds)}">${esc(title)}</div>
        <div class="card-sub" title="完整时间 ${esc(c.abs_seconds)}">${sub}</div>
      </div>
      <div class="card-right">${milestones}${here}</div>
    </div>
    <div class="files">${filesHtml}</div>
    <div class="actions">
      <button class="btn primary" data-act="restore-version"
              title="把这一版另存一份放到文件夹旁边,不动你现在正在用的文件">还原这一版</button>
      <button class="btn" data-act="note" title="给这一版起个你记得住的名字">${c.note ? "改备注" : "加备注"}</button>
      ${delNoteBtn}
      <button class="btn" data-act="tag" title="把这一版标记为重要节点(★)">标里程碑</button>
    </div>`;
  return el;
}

function fileIcon(name) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  const map = {
    docx: ["W", "#2b579a"], doc: ["W", "#2b579a"], pdf: ["P", "#dc2626"],
    xlsx: ["X", "#217346"], pptx: ["P", "#d24726"], md: ["M", "#6b7280"], txt: ["T", "#6b7280"],
  };
  const [letter, color] = map[ext] || [(ext[0] || "?").toUpperCase(), "#6b7280"];
  return `<div class="ficon" style="background:${color}">${esc(letter)}</div>`;
}

function arrow(sign) {
  if (sign === "up") return '<span class="up">▲</span>';
  if (sign === "down") return '<span class="down">▼</span>';
  return "";
}

function onAlbumClick(e) {
  const btn = e.target.closest("button");
  if (!btn) return;
  const card = btn.closest(".card");
  const fullId = card.dataset.id;
  const act = btn.dataset.act;
  if (act === "restore-version") {
    openConfirm(card, "把这一版另存一份放到文件夹旁边,不会动你现在正在用的文件。", () => doRestoreVersion(fullId));
  } else if (act === "note") {
    openInput(card, "给这一版起个名字(如:导师说结论太弱)", (txt) => pywebview.api.set_note(CURRENT_FOLDER, fullId, txt));
  } else if (act === "tag") {
    openInput(card, "里程碑名称(如:投稿前)", (txt) => pywebview.api.set_tag(CURRENT_FOLDER, fullId, txt));
  } else if (act === "del-note") {
    // 删标签≠删版本=完全可逆:直接删 + 撤销 toast(撤销靠缓存原文精确恢复,不靠用户记忆)
    const old = (CARDS.find((x) => x.full_id === fullId) || {}).note || "";
    delAnnotation(
      () => pywebview.api.set_note(CURRENT_FOLDER, fullId, ""),
      "已删除备注",
      () => pywebview.api.set_note(CURRENT_FOLDER, fullId, old));
  } else if (act === "del-tag") {
    const name = btn.dataset.tag;
    delAnnotation(
      () => pywebview.api.remove_tag(CURRENT_FOLDER, name),
      `已删除里程碑「${name}」`,
      () => pywebview.api.set_tag(CURRENT_FOLDER, fullId, name));
  }
}

async function delAnnotation(doDelete, msg, doUndo) {
  try {
    await doDelete();
    await loadFolder(CURRENT_FOLDER);
    undoToast(msg, doUndo);
  } catch (e) { showError(e); }
}

async function doRestoreVersion(fullId) {
  try {
    const r = await pywebview.api.restore_version(CURRENT_FOLDER, fullId);
    await loadFolder(CURRENT_FOLDER);            // 先刷新出新版本
    showRestoreResult(r.restored_paths || []);   // 再亮持久提示(banner 在 album 外,不被 reload 清掉)
  } catch (e) { showError(e); }
}

// 还原闭环:持久提示(不自动消失)+ 一键在访达里定位刚还原出的副本,别让用户找不到
function showRestoreResult(paths) {
  const box = document.getElementById("restoreResult");
  const names = paths.map((p) => String(p).split(/[\\/]/).pop());
  box.innerHTML =
    `<span class="msg">✅ 已另存到文件夹旁边：${esc(names.join("、"))}（没动你现在正在用的文件）</span>` +
    `<button class="btn small primary" data-x="open">📂 在访达中打开</button>` +
    `<button class="btn small ghost" data-x="close">知道了</button>`;
  box.hidden = false;
  box.onclick = (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.dataset.x === "open" && paths.length) {
      pywebview.api.reveal_path(paths[0]).catch(showError);   // open -R 选中副本
    }
    box.hidden = true;
  };
}

function openConfirm(card, message, onOk) {
  const old = card.querySelector(".inline-input");
  if (old) old.remove();
  const box = document.createElement("div");
  box.className = "inline-input confirm";
  box.innerHTML = `
    <span class="confirm-msg">${esc(message)}</span>
    <div class="confirm-btns">
      <button class="btn small primary" data-x="ok">确定还原</button>
      <button class="btn small ghost" data-x="cancel">取消</button>
    </div>`;
  card.appendChild(box);
  box.addEventListener("click", async (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.dataset.x === "cancel") return box.remove();
    box.remove();
    await onOk();
  });
}

function openInput(card, placeholder, onSubmit) {
  const old = card.querySelector(".inline-input");
  if (old) old.remove();
  const box = document.createElement("div");
  box.className = "inline-input";
  box.innerHTML = `
    <input type="text" placeholder="${esc(placeholder)}">
    <button class="btn small" data-x="ok">确定</button>
    <button class="btn small ghost" data-x="cancel">取消</button>`;
  card.appendChild(box);
  const input = box.querySelector("input");
  input.focus();
  box.addEventListener("click", async (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.dataset.x === "cancel") return box.remove();
    const v = input.value.trim();
    if (!v) return box.remove();
    try { await onSubmit(v); await loadFolder(CURRENT_FOLDER); toast("已保存"); }
    catch (e) { showError(e); }
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") box.querySelector('[data-x="ok"]').click();
    if (e.key === "Escape") box.remove();
  });
}

// ==================== 工具 ====================
function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
let UNDO_T = null;
function toast(msg) {
  const t = document.getElementById("toast");
  clearTimeout(UNDO_T);
  t.textContent = msg;
  t.className = "toast show";
  setTimeout(() => (t.className = "toast"), 2800);
}
// 删备注/里程碑后的可撤销提示:撤销精确恢复原值(重 set),6 秒后自动消失
function undoToast(msg, onUndo) {
  const t = document.getElementById("toast");
  clearTimeout(UNDO_T);
  t.innerHTML = `<span>${esc(msg)}</span><button class="toast-undo" type="button">撤销</button>`;
  t.className = "toast show";
  t.querySelector(".toast-undo").onclick = async () => {
    clearTimeout(UNDO_T);
    t.className = "toast";
    try { await onUndo(); await loadFolder(CURRENT_FOLDER); toast("已恢复"); }
    catch (e) { showError(e); }
  };
  UNDO_T = setTimeout(() => { t.className = "toast"; t.textContent = ""; }, 6000);
}
function showError(e) {
  toast("⚠️ " + (e && e.message ? e.message : e));
}
