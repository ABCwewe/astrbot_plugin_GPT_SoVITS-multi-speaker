const bridge = window.AstrBotPluginPage;
let config = {};
let providers = [];
let selectedSpeakerIdx = 0;
let expandedEmotions = new Set();
let speakerScrollTarget = null; // null | 'selected' | 'bottom'

// ===== Utilities =====
const $ = (id) => document.getElementById(id);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const esc = (s) => s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : '';
const deepClone = (x) => JSON.parse(JSON.stringify(x));

function g(path, def) {
  const keys = path.split('.');
  let v = config;
  for (const k of keys) {
    if (v == null || typeof v !== 'object') return def;
    v = v[k];
  }
  return v !== undefined ? v : def;
}

function s(path, val) {
  const keys = path.split('.');
  let o = config;
  for (let i = 0; i < keys.length - 1; i++) {
    if (!(keys[i] in o) || typeof o[keys[i]] !== 'object' || o[keys[i]] === null) o[keys[i]] = {};
    o = o[keys[i]];
  }
  o[keys[keys.length - 1]] = val;
}

function setStatus(text, cls) {
  const el = $('status');
  if (el) { el.textContent = text; el.className = 'badge ' + cls; }
}

// ===== Init =====
async function init() {
  try {
    setStatus('加载中...', 'loading');
    config = await bridge.apiGet('config');
    try {
      const provRes = await bridge.apiGet('providers');
      providers = provRes.providers || [];
    } catch (e) { providers = []; }
    bindTabs();
    $('btn-save').onclick = save;
    renderTab('basic');
    setStatus('已加载', 'ok');
  } catch (e) {
    setStatus('加载失败: ' + e.message, 'err');
  }
}

// ===== Tab Navigation =====
function bindTabs() {
  $$('#tabs .tab').forEach(btn => {
    btn.onclick = () => {
      $$('#tabs .tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderTab(btn.dataset.tab);
    };
  });
}

function renderTab(tab) {
  const content = $('content');
  if (!content) return;
  const renderers = { basic: renderBasic, speakers: renderSpeakers, tts: renderTTS, auto: renderAuto, judge: renderJudge, cache: renderCache };
  const fn = renderers[tab];
  if (!fn) { content.innerHTML = ''; return; }
  const html = fn();
  if (tab === 'speakers') {
    content.innerHTML = html;
    bindControls();
    bindSpeakerControls();
    scrollSpeakerListToTarget();
  } else {
    content.innerHTML = `<div class="content-scroll">${html}</div>`;
    bindControls();
  }
}

// ===== Form Components =====
function toggle(path, label, hint) {
  const val = g(path, false);
  return `<label class="fg fg-toggle">
    <span class="fg-label">${label}</span>
    <input type="checkbox" data-path="${path}" ${val ? 'checked' : ''}>
    <span class="switch"></span>
  </label>${hint ? `<div class="fg-hint" style="margin-top:-8px;margin-bottom:12px;padding-left:16px;">${hint}</div>` : ''}`;
}

function textInput(path, label, hint, placeholder, style) {
  const val = g(path, '');
  return `<div class="fg" style="${style || ''}">
    <span class="fg-label">${label}</span>
    <input type="text" data-path="${path}" value="${esc(val)}" placeholder="${esc(placeholder || '')}">
    ${hint ? `<div class="fg-hint">${hint}</div>` : ''}
  </div>`;
}

function textArea(path, label, hint, rows) {
  const val = g(path, '');
  return `<div class="fg fg-full">
    <span class="fg-label">${label}</span>
    <textarea data-path="${path}" rows="${rows || 3}">${esc(val)}</textarea>
    ${hint ? `<div class="fg-hint">${hint}</div>` : ''}
  </div>`;
}

function selectInput(path, label, options, hint) {
  const val = g(path, '');
  const opts = options.map(([v, l]) => `<option value="${v}" ${val === v ? 'selected' : ''}>${l}</option>`).join('');
  return `<div class="fg">
    <span class="fg-label">${label}</span>
    <select data-path="${path}">${opts}</select>
    ${hint ? `<div class="fg-hint">${hint}</div>` : ''}
  </div>`;
}

function sliderInput(path, label, min, max, step, hint) {
  const val = g(path, 0);
  return `<div class="fg fg-slider">
    <span class="fg-label">${label}</span>
    <div class="slider-row">
      <input type="range" data-path="${path}" min="${min}" max="${max}" step="${step}" value="${val}">
      <span class="slider-value" data-slider-val="${path}">${val}</span>
    </div>
    ${hint ? `<div class="fg-hint">${hint}</div>` : ''}
  </div>`;
}

// ===== Tab: Basic =====
function renderBasic() {
  const speakerNames = (g('speakers', []) || []).map(sp => sp.speaker_name || '');
  const currentDefault = g('default_speaker', '');
  const speakerOpts = speakerNames.map(n => `<option value="${esc(n)}" ${n === currentDefault ? 'selected' : ''}>${esc(n)}</option>`).join('');
  return `
    <div class="section-title">基础设置</div>
    ${toggle('enabled', '插件总开关', 'GPT-SoVITS 插件总开关，请在部署好 GPT-SoVITS 后再打开此开关')}
    <div class="card">
      <div class="card-title">默认说话人</div>
      <div class="fg">
        <span class="fg-label">默认说话人名称</span>
        <select data-path="default_speaker">
          ${speakerOpts || '<option value="">暂无说话人</option>'}
        </select>
        <div class="fg-hint">在不指定说话人时使用的默认说话人名称</div>
      </div>
    </div>
    <div class="hint-box">
      💡 提示：请先在「说话人管理」中配置说话人，然后在此处选择默认说话人。部署好 GPT-SoVITS API 后再打开总开关。
    </div>
  `;
}

// ===== Tab: Speakers =====
function renderSpeakers() {
  const speakers = g('speakers', []);
  if (!speakers.length) {
    return `
      <div class="section-title">说话人管理</div>
      <div class="empty-state">
        <p>暂无说话人配置</p>
        <button class="btn btn-sm" data-action="add-speaker" style="margin-top:12px">+ 添加说话人</button>
      </div>
    `;
  }

  if (selectedSpeakerIdx >= speakers.length) selectedSpeakerIdx = 0;

  const listHtml = speakers.map((sp, i) => {
    const name = sp.speaker_name || '未命名';
    const emoCount = getEmotionCount(sp);
    const isDefault = sp.speaker_name === g('default_speaker', '');
    return `<div class="speaker-item ${i === selectedSpeakerIdx ? 'active' : ''}" data-speaker-idx="${i}">
      <span class="name">${esc(name)}</span>
      ${isDefault ? '<span class="default-badge">默认</span>' : ''}
      <span class="emotion-count">${emoCount} 情绪</span>
    </div>`;
  }).join('');

  return `
    <div class="section-title">说话人管理</div>
    <div class="speakers-layout">
      <div class="speakers-list">
        <div class="speakers-list-header">
          <span class="list-title">${speakers.length} 个说话人</span>
          <button class="btn btn-sm" data-action="add-speaker">+ 添加</button>
        </div>
        <div class="speakers-list-items">
          ${listHtml}
        </div>
      </div>
      <div class="speaker-editor">
        ${renderSpeakerEditor(selectedSpeakerIdx)}
      </div>
    </div>
  `;
}

function getEmotionCount(speaker) {
  const emotions = speaker.emotions;
  if (Array.isArray(emotions)) return emotions.length;
  if (typeof emotions === 'string') {
    try { return JSON.parse(emotions).length; } catch { return 0; }
  }
  return 0;
}

function renderSpeakerEditor(idx) {
  const sp = g('speakers', [])[idx];
  if (!sp) return '<div class="empty-state">请选择一个说话人</div>';

  const langOptions = [['zh','中文'],['en','英语'],['ja','日语'],['ko','韩语'],['zh_ja_auto','中日自动']];

  return `
    <div class="card">
      <div class="card-title">说话人信息</div>
      <div class="row">
        ${textInput(`speakers.${idx}.speaker_name`, '说话人名称', '说话人的唯一标识名称，用于指令中指定', 'default', 'flex:1;min-width:200px')}
        ${textInput(`speakers.${idx}.alias`, '说话人别名', '多个用逗号分隔，如：小明,xm', '', 'flex:1;min-width:200px')}
      </div>
      <div class="row">
        ${textInput(`speakers.${idx}.gpt_path`, 'GPT 模型路径', "即'.ckpt'后缀的文件，不填则用 GPT-SoVITS 内置模型", 'GPT-SoVITS/gpt.ckpt')}
        ${textInput(`speakers.${idx}.sovits_path`, 'SoVITS 模型路径', "即'.pth'后缀的文件，不填则用 GPT-SoVITS 内置模型", 'GPT-SoVITS/sovits.pth')}
      </div>
      <div class="row">
        ${textInput(`speakers.${idx}.base_url`, 'API 服务器地址', '此说话人使用的 GPT-SoVITS API 地址', 'http://127.0.0.1:9880')}
        ${sliderInput(`speakers.${idx}.timeout`, 'API 超时时间 (秒)', 30, 180, 1)}
        ${selectInput(`speakers.${idx}.text_lang`, '默认合成语言', langOptions)}
      </div>
      <button class="btn btn-sm btn-danger" data-action="delete-speaker" data-idx="${idx}" style="margin-top:8px">🗑 删除此说话人</button>
    </div>

    <div class="emotions-section">
      ${renderEmotionEditor(idx)}
    </div>
  `;
}

// ===== Emotion Visual Editor =====
function renderEmotionEditor(speakerIdx) {
  const emotions = getEmotions(speakerIdx);

  const cardsHtml = emotions.map((emo, emoIdx) => {
    const key = `${speakerIdx}-${emoIdx}`;
    const expanded = expandedEmotions.has(key);
    const name = emo.name || '未命名情绪';
    const keywords = emo.keywords || [];
    const keywordTags = keywords.slice(0, 4).map(k => `<span class="emo-tag">${esc(k)}</span>`).join('');
    const moreCount = keywords.length > 4 ? `<span class="emo-tag">+${keywords.length - 4}</span>` : '';

    return `
      <div class="emotion-card ${expanded ? 'expanded' : ''}" data-emotion-card="${key}">
        <div class="emotion-header" data-toggle-emotion="${key}">
          <span class="toggle-icon">▶</span>
          <span class="emo-name">${esc(name)}</span>
          <div class="emo-tags">${keywordTags}${moreCount}</div>
          <button class="btn btn-sm btn-danger" data-action="delete-emotion" data-speaker-idx="${speakerIdx}" data-emotion-idx="${emoIdx}">✕</button>
        </div>
        <div class="emotion-body">
          ${renderEmotionFields(speakerIdx, emoIdx, emo)}
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="card">
      <div class="card-title">情绪配置 (${emotions.length} 个)</div>
      <div class="fg-hint" style="margin-bottom:12px">每个情绪包含参考音频、文本、语言、语速等参数。情绪匹配优先级：指令指定 &gt; LLM 判断 &gt; 关键词匹配。</div>
      ${cardsHtml || '<div class="empty-state">暂无情绪配置，点击下方按钮添加</div>'}
      <button class="btn-add" data-action="add-emotion" data-speaker-idx="${speakerIdx}">+ 添加情绪</button>
    </div>
  `;
}

function renderEmotionFields(speakerIdx, emoIdx, emo) {
  const langOptions = [['zh','中文'],['en','英语'],['ja','日语'],['ko','韩语']];
  const p = (field) => `speakers.${speakerIdx}.emotions.${emoIdx}.${field}`;

  return `
    <div class="row">
      <div class="fg" style="flex:1;min-width:200px">
        <span class="fg-label">情绪名称</span>
        <input type="text" data-path="${p('name')}" value="${esc(emo.name || '')}" placeholder="如：开心">
      </div>
      <div class="fg" style="width:160px;flex:0 0 160px">
        <span class="fg-label">参考音频语言</span>
        <select data-path="${p('prompt_lang')}">
          ${langOptions.map(([v,l]) => `<option value="${v}" ${(emo.prompt_lang || 'zh') === v ? 'selected' : ''}>${l}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="fg fg-full">
      <span class="fg-label">触发关键词</span>
      ${renderKeywordEditor(p('keywords'), emo.keywords || [])}
      <div class="fg-hint">当文本包含这些关键词时，会匹配到此情绪（仅在未使用 LLM 判断时生效）</div>
    </div>
    <div class="fg fg-full">
      <span class="fg-label">参考音频路径</span>
      <input type="text" data-path="${p('ref_audio_path')}" value="${esc(emo.ref_audio_path || '')}" placeholder="path/to/reference.wav">
    </div>
    <div class="fg fg-full">
      <span class="fg-label">参考音频文本</span>
      <input type="text" data-path="${p('prompt_text')}" value="${esc(emo.prompt_text || '')}" placeholder="参考音频对应的文本内容">
    </div>
    <div class="row">
      ${sliderInput(p('speed_factor'), '语速倍数', 0.5, 2.0, 0.1, '1.0 为正常速度，大于 1 加速，小于 1 减速')}
      ${sliderInput(p('fragment_interval'), '片段间隔', 0.1, 2.0, 0.1, '控制语音片段之间的停顿时间')}
    </div>
  `;
}

function renderKeywordEditor(path, keywords) {
  const tags = keywords.map((kw, i) =>
    `<span class="keyword-tag">${esc(kw)}<span class="remove" data-action="remove-keyword" data-path="${path}" data-idx="${i}">×</span></span>`
  ).join('');
  return `<div class="keyword-input-wrap">
    ${tags}
    <input type="text" class="keyword-input" data-action="add-keyword" data-path="${path}" placeholder="输入关键词后回车...">
  </div>`;
}

function getEmotions(speakerIdx) {
  const speaker = g('speakers', [])[speakerIdx];
  if (!speaker) return [];
  let emotions = speaker.emotions;
  if (typeof emotions === 'string') {
    try { emotions = JSON.parse(emotions); } catch { emotions = []; }
  }
  if (!Array.isArray(emotions)) emotions = [];
  return emotions;
}

// ===== Tab: TTS Params =====
function renderTTS() {
  const mediaOpts = [['wav','WAV'],['mp3','MP3'],['ogg','OGG']];
  const splitOpts = [['cut0','不切分'],['cut1','四句一切'],['cut2','50字一切'],['cut3','按中文句号切'],['cut4','按英文句号切'],['cut5','按标点符号切']];
  return `
    <div class="section-title">TTS 全局参数</div>
    <div class="card">
      <div class="card-title">合成参数</div>
      <div class="row">
        ${selectInput('tts_params.media_type', '输出音频格式', mediaOpts, '建议 wav，兼容性好')}
        ${selectInput('tts_params.text_split_method', '文本切分方式', splitOpts, '影响长文本处理效果')}
      </div>
      <div class="row">
        ${sliderInput('tts_params.batch_size', '推理批大小', 1, 10, 1, '越大越快但越占显存')}
        ${sliderInput('tts_params.batch_threshold', '批处理阈值', 0.1, 1.0, 0.01, '控制是否拆分批次')}
      </div>
      <div class="row">
        ${toggle('tts_params.parallel_infer', '启用并行推理', '开启后可提升速度，建议开启')}
        ${toggle('tts_params.split_bucket', '启用分桶推理', '开启后可并行处理长文本，建议开启')}
      </div>
    </div>
  `;
}

// ===== Tab: Auto =====
function renderAuto() {
  return `
    <div class="section-title">自动触发配置</div>
    <div class="hint-box">
      💡 本插件有一定概率主动将 bot 本来要发送的文本转成语音发送。自动触发仅处理纯文本消息。
    </div>
    <div class="card">
      <div class="card-title">触发条件</div>
      ${toggle('auto.only_llm_result', '只处理 LLM 结果', '只处理 LLM 返回的消息，建议打开')}
      <div class="row">
        ${sliderInput('auto.tts_prob', '主动转语音概率', 0, 1, 0.01, 'Bot 回复时自动转语音的概率，0 为不触发，1 为总是触发')}
        ${sliderInput('auto.max_msg_len', '文本长度限制', 0, 200, 1, '超过此长度的文本不会被转成语音发送')}
      </div>
    </div>
  `;
}

// ===== Tab: Judge =====
function renderJudge() {
  const providerOpts = [
    ['', '跟随当前会话模型'],
    ...providers.map(p => [p.id, `${p.name} (${p.id})`])
  ];
  return `
    <div class="section-title">情感判断配置</div>
    <div class="card">
      <div class="card-title">LLM 情感判断</div>
      ${toggle('judge.enabled_llm', '使用 LLM 判断情感', '开启后，将使用 LLM 模型判断当前文本的情绪，从而改变语音的情绪参数。若关闭，则使用情绪条目的触发词来匹配情绪')}
      ${toggle('judge.enabled_command', '指令触发时启用 LLM 情感判断', '控制指令触发的语音合成是否使用 LLM 进行情感判断。关闭时所有指令合成跳过 LLM 判断；开启时如果说话人只有1个情绪预设则跳过 LLM 判断')}
      <div class="fg">
        <span class="fg-label">判断情感用的 LLM 提供商</span>
        <select data-path="judge.provider_id">
          ${providerOpts.map(([v,l]) => `<option value="${esc(v)}" ${g('judge.provider_id','') === v ? 'selected' : ''}>${esc(l)}</option>`).join('')}
        </select>
        <div class="fg-hint">留空时使用当前正在使用的 LLM 提供商。工作较为简单，建议用稳定便宜又快速的小模型</div>
      </div>
    </div>
  `;
}

// ===== Tab: Cache =====
function renderCache() {
  return `
    <div class="section-title">缓存设置</div>
    <div class="card">
      <div class="card-title">语音缓存</div>
      ${toggle('cache.enabled', '启用语音缓存', '开启后，请求参数一致时直接复用本地缓存音频，减少重复推理')}
      <div class="row">
        ${sliderInput('cache.expire_hours', '缓存过期时间 (小时)', 0, 240, 1, '0 表示永不过期，大于 0 时按文件修改时间判断是否过期')}
      </div>
      <div class="fg fg-full">
        <span class="fg-label">缓存路径</span>
        <input type="text" value="data/plugin_data/astrbot_plugin_GPT_SoVITS/audio" disabled>
        <div class="fg-hint">缓存路径由系统自动管理，使用插件专属数据目录，无需手动配置</div>
      </div>
    </div>
  `;
}

// ===== Bind Controls =====
function bindControls() {
  $$('#content input[type="checkbox"][data-path]').forEach(el => {
    el.onchange = () => { s(el.dataset.path, el.checked); setStatus('未保存', 'warn'); };
  });
  $$('#content input[type="text"][data-path], #content textarea[data-path], #content select[data-path]').forEach(el => {
    el.oninput = el.onchange = () => { s(el.dataset.path, el.value); setStatus('未保存', 'warn'); };
  });
  $$('#content input[type="range"][data-path]').forEach(el => {
    el.oninput = () => {
      const val = parseFloat(el.value);
      s(el.dataset.path, val);
      const valEl = document.querySelector(`[data-slider-val="${el.dataset.path}"]`);
      if (valEl) valEl.textContent = val;
      setStatus('未保存', 'warn');
    };
  });
  $$('#content [data-action="remove-keyword"]').forEach(el => {
    el.onclick = (e) => {
      e.stopPropagation();
      const path = el.dataset.path;
      const idx = parseInt(el.dataset.idx);
      const arr = g(path, []);
      arr.splice(idx, 1);
      s(path, arr);
      renderCurrentTab();
      bindControls();
    };
  });
  $$('#content [data-action="add-keyword"]').forEach(el => {
    el.onkeydown = (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const path = el.dataset.path;
        const val = el.value.trim();
        if (val) {
          const arr = g(path, []);
          if (!arr.includes(val)) arr.push(val);
          s(path, arr);
          renderCurrentTab();
          bindControls();
        }
      }
    };
  });
}

function renderCurrentTab() {
  const activeTab = $('.tab.active');
  if (activeTab) renderTab(activeTab.dataset.tab);
}

function scrollSpeakerListToTarget() {
  requestAnimationFrame(() => {
    if (speakerScrollTarget === 'bottom') {
      const listItems = document.querySelector('.speakers-list-items');
      if (listItems) listItems.scrollTop = listItems.scrollHeight;
    } else if (speakerScrollTarget === 'selected') {
      const active = document.querySelector('.speaker-item.active');
      if (active) active.scrollIntoView({ block: 'nearest', behavior: 'auto' });
    }
    speakerScrollTarget = null;
  });
}

function updateSpeakerEditor() {
  const editor = document.querySelector('.speaker-editor');
  if (!editor) return;
  editor.innerHTML = renderSpeakerEditor(selectedSpeakerIdx);
  bindControls();
  bindSpeakerEditorControls();
  editor.scrollTop = 0;
}

function updateSpeakerActiveClass() {
  $$('.speaker-item').forEach((el, i) => {
    el.classList.toggle('active', i === selectedSpeakerIdx);
  });
}

function bindSpeakerEditorControls() {
  $$('#content [data-action="delete-speaker"]').forEach(el => {
    el.onclick = () => {
      const idx = parseInt(el.dataset.idx);
      const speakers = g('speakers', []);
      speakers.splice(idx, 1);
      s('speakers', speakers);
      if (selectedSpeakerIdx >= speakers.length) selectedSpeakerIdx = Math.max(0, speakers.length - 1);
      expandedEmotions.clear();
      speakerScrollTarget = 'selected';
      renderTab('speakers');
      bindSpeakerControls();
      bindControls();
      setStatus('未保存', 'warn');
    };
  });
  $$('#content [data-action="add-emotion"]').forEach(el => {
    el.onclick = () => {
      const spIdx = parseInt(el.dataset.speakerIdx);
      const emotions = getEmotions(spIdx);
      emotions.push({
        name: '新情绪',
        keywords: [],
        ref_audio_path: '',
        prompt_text: '',
        prompt_lang: 'zh',
        speed_factor: 1.0,
        fragment_interval: 0.7
      });
      s(`speakers.${spIdx}.emotions`, emotions);
      expandedEmotions.add(`${spIdx}-${emotions.length - 1}`);
      speakerScrollTarget = 'selected';
      renderTab('speakers');
      bindSpeakerControls();
      bindControls();
      setStatus('未保存', 'warn');
    };
  });
  $$('#content [data-action="delete-emotion"]').forEach(el => {
    el.onclick = (e) => {
      e.stopPropagation();
      const spIdx = parseInt(el.dataset.speakerIdx);
      const emoIdx = parseInt(el.dataset.emotionIdx);
      const emotions = getEmotions(spIdx);
      emotions.splice(emoIdx, 1);
      s(`speakers.${spIdx}.emotions`, emotions);
      expandedEmotions.clear();
      speakerScrollTarget = 'selected';
      renderTab('speakers');
      bindSpeakerControls();
      bindControls();
      setStatus('未保存', 'warn');
    };
  });
  $$('#content [data-toggle-emotion]').forEach(el => {
    el.onclick = () => {
      const key = el.dataset.toggleEmotion;
      if (expandedEmotions.has(key)) expandedEmotions.delete(key);
      else expandedEmotions.add(key);
      speakerScrollTarget = 'selected';
      renderTab('speakers');
      bindSpeakerControls();
      bindControls();
    };
  });
}

// ===== Speaker Controls =====
function bindSpeakerControls() {
  $$('#content [data-speaker-idx]').forEach(el => {
    el.onclick = () => {
      selectedSpeakerIdx = parseInt(el.dataset.speakerIdx);
      expandedEmotions.clear();
      updateSpeakerActiveClass();
      updateSpeakerEditor();
    };
  });
  $$('#content [data-action="add-speaker"]').forEach(el => {
    el.onclick = () => {
      const speakers = g('speakers', []);
      speakers.push({
        speaker_name: 'speaker_' + (speakers.length + 1),
        alias: '',
        gpt_path: '',
        sovits_path: '',
        base_url: 'http://127.0.0.1:9880',
        timeout: 60,
        text_lang: 'zh',
        emotions: [{ name: '默认', keywords: [], ref_audio_path: '', prompt_text: '', prompt_lang: 'zh', speed_factor: 1.0, fragment_interval: 0.7 }]
      });
      s('speakers', speakers);
      selectedSpeakerIdx = speakers.length - 1;
      expandedEmotions.clear();
      speakerScrollTarget = 'bottom';
      renderTab('speakers');
      bindSpeakerControls();
      bindControls();
      setStatus('未保存', 'warn');
    };
  });
  bindSpeakerEditorControls();
}

// ===== Save =====
async function save() {
  try {
    setStatus('保存中...', 'warn');
    const data = deepClone(config);
    const r = await bridge.apiPost('config', data);
    if (r.success !== false) {
      setStatus('已保存 ✓', 'ok');
    } else {
      throw new Error(r.error || r.message || '保存失败');
    }
  } catch (e) {
    setStatus('错误: ' + e.message, 'err');
  }
}

// ===== Start =====
bridge.ready().then(() => init());
