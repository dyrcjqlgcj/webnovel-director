# 仪表盘前端重写

文件: C:\Users\ThinkPad\.openclaw\skills\webnovel-director\scripts\dashboard_server.py

## 要求
完全重写 HTML_TEMPLATE，保留所有后端Python逻辑不变。

## 新设计
1. 深色主题，顶部项目名+状态色块
2. 三个操作按钮：一键体检(蓝色) / 大纲审查 / 刷新
3. 章节表格：每行显示 章号|标题|字数|评分(A-F彩色)|状态|审查按钮
4. 评分计算：有正文+1,有Goal+1,有MustHit+1,审查PASS+2/WARN+1/FAIL+0 → 5=A,4=B,3=C,2=D,<2=-
5. 侧边栏：进度条+统计+最近审计
6. 自动30秒刷新
7. 点击行弹出详情modal

## JS初始化流程
```js
// 页面加载后立即获取数据并渲染
async function init() {
  try {
    const r = await fetch('/api/state');
    const data = await r.json();
    render(data);
    // 自动刷新
    setInterval(async () => {
      const r2 = await fetch('/api/state');
      render(await r2.json());
    }, 30000);
  } catch(e) { console.error(e); }
}
document.addEventListener('DOMContentLoaded', init);
```

## 评分函数
```js
function calcScore(c) {
  let s = 0;
  if (c.words > 0) s++;
  if (c.goal && c.goal.length > 3 && c.goal !== '未设定') s++;
  if (c.premise_hit && c.premise_hit.length > 3 && c.premise_hit !== '未设定') s++;
  if (c.review_verdict === 'PASS') s += 2;
  else if (c.review_verdict === 'WARN') s++;
  else if (c.words > 0) s++;  // written but not reviewed
  const grades = ['F','D','C','B','A'];
  if (s >= 5) return {grade:'A', color:'#22c55e'};
  if (s >= 4) return {grade:'B', color:'#10b981'};
  if (s >= 3) return {grade:'C', color:'#eab308'};
  if (s >= 2) return {grade:'D', color:'#f97316'};
  return {grade:'-', color:'#6b7280'};
}
```

## 表行动态生成
```js
function renderTable(chapters) {
  return chapters.map(c => {
    const sc = calcScore(c);
    const title = c.title || ('第' + c.chapter + '章');
    const words = (c.words || 0);
    const status = c.status || 'QUEUE';
    const statusColor = status.toUpperCase().includes('WRITTEN') ? '#22c55e' :
                        status.toUpperCase().includes('WARN') ? '#eab308' :
                        status.toUpperCase().includes('FAIL') ? '#ef4444' : '#6b7280';
    return `<tr onclick="showDetail(${c.chapter})" style="cursor:pointer">
      <td>${c.chapter}</td>
      <td>${esc(title)}</td>
      <td style="text-align:right">${words || '-'}</td>
      <td style="text-align:center;font-weight:700;color:${sc.color}">${sc.grade}</td>
      <td><span style="color:${statusColor};font-size:11px">${status}</span></td>
      <td><button onclick="event.stopPropagation();doAction('review_ch_${c.chapter}')" style="padding:2px 6px;font-size:11px">审</button></td>
    </tr>`;
  }).join('');
}
```

## 关键点
- 必须用 DOMContentLoaded 初始化（不是直接调refresh）
- render() 中 getElementById 前确保元素存在
- escape HTML 防止XSS
- 按钮action保留doctor/review/review_ch_

完成后: python -m py_compile 验证 + 重启仪表盘测试
