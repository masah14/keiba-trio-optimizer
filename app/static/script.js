// 競馬三連複 最適化戦略アプリ

// 今日のレースを取得
async function scrapeTodayRaces() {
    const statusEl = document.getElementById('scrape-status');
    statusEl.textContent = '取得中...';
    statusEl.className = 'status loading';

    try {
        // まずスクレイピング
        const scrapeRes = await fetch('/api/scrape-today', { method: 'POST' });
        const scrapeData = await scrapeRes.json();

        // レース一覧を取得
        await loadTodayRaces();

        statusEl.textContent = `${scrapeData.scraped_count}件のレースを取得しました`;
        statusEl.className = 'status success';

    } catch (err) {
        console.error('Error:', err);
        statusEl.textContent = 'エラーが発生しました';
        statusEl.className = 'status error';
    }
}

// 今日のレース一覧を読み込み
async function loadTodayRaces() {
    try {
        const res = await fetch('/api/today-races');
        const data = await res.json();

        // 日付範囲を表示
        const dateRangeEl = document.getElementById('date-range-info');
        if (data.date_range) {
            const formatDate = (d) => `${d.slice(4, 6)}/${d.slice(6, 8)}`;
            dateRangeEl.innerHTML = `対象期間: ${formatDate(data.date_from)} 〜 ${formatDate(data.date_to)}（${data.date_range.length}日間）/ 全${data.total_races || 0}レース`;
        }

        const container = document.getElementById('race-list');

        // 対象レースと対象外レースを取得
        const targetRaces = data.target_races || data.races || [];
        const otherRaces = data.other_races || [];

        if (targetRaces.length === 0 && otherRaces.length === 0) {
            container.innerHTML = `
                <div class="no-races">
                    <p>レースがありません</p>
                    <p class="hint">「レースを取得」ボタンをクリックしてください</p>
                    <p class="hint">※1月5日以降のJRA開催日にレースが表示されます</p>
                </div>
            `;
            return;
        }

        container.innerHTML = '';

        // 対象レースを表示
        if (targetRaces.length > 0) {
            const targetHeader = document.createElement('div');
            targetHeader.className = 'section-header target';
            targetHeader.innerHTML = `<h2>🎯 対象レース（${targetRaces.length}件）</h2><span>GIII / 1勝 / 2勝 / 未勝利</span>`;
            container.appendChild(targetHeader);

            renderRacesByDate(container, targetRaces, true);
        }

        // 対象外レースを表示
        if (otherRaces.length > 0) {
            const otherHeader = document.createElement('div');
            otherHeader.className = 'section-header other';
            otherHeader.innerHTML = `<h2>📋 その他のレース（${otherRaces.length}件）</h2><span>GI / GII / OP など</span>`;
            container.appendChild(otherHeader);

            renderRacesByDate(container, otherRaces, false);
        }

    } catch (err) {
        console.error('Error loading races:', err);
    }
}

// 日付ごとにレースを描画
function renderRacesByDate(container, races, isTarget) {
    // 日付でグループ化
    const racesByDate = {};
    races.forEach(race => {
        const date = race.date || 'unknown';
        if (!racesByDate[date]) racesByDate[date] = [];
        racesByDate[date].push(race);
    });

    // 日付ごとに表示
    Object.keys(racesByDate).sort().forEach(date => {
        const dateRaces = racesByDate[date];
        const formatDate = (d) => `${d.slice(0, 4)}年${d.slice(4, 6)}月${d.slice(6, 8)}日`;

        const dateHeader = document.createElement('div');
        dateHeader.className = 'date-header';
        dateHeader.innerHTML = `<h3>${formatDate(date)}</h3><span>${dateRaces.length}レース</span>`;
        container.appendChild(dateHeader);

        const raceGrid = document.createElement('div');
        raceGrid.className = 'race-grid';

        dateRaces.forEach(race => {
            const div = document.createElement('div');
            div.className = `race-item ${isTarget ? 'target' : 'other'}`;
            div.onclick = () => loadRaceDetail(race.race_id);

            const distanceLabel = race.distance ? getDistanceLabel(race.distance) : '';
            const classLabel = getClassLabel(race.class);
            const horseInfo = race.horse_count > 0 ? `${race.horse_count}頭` : '枠順未定';
            const trackInfo = race.track_name ? `${race.track_name}${race.race_num}R` : '';

            div.innerHTML = `
                <div class="race-item-header">
                    ${trackInfo ? `<span class="badge-track">${trackInfo}</span>` : ''}
                    ${classLabel}
                    ${distanceLabel}
                </div>
                <div class="race-item-name">${race.name || 'レース' + race.race_id.slice(-2)}</div>
                <div class="race-item-meta">${race.course || ''} ${race.distance ? '/ ' + race.distance + 'm' : ''} / ${horseInfo}</div>
            `;

            raceGrid.appendChild(div);
        });

        container.appendChild(raceGrid);
    });
}

// クラスラベル
function getClassLabel(raceClass) {
    if (raceClass === 'GIII') return '<span class="badge-giii">GIII</span>';
    if (raceClass === 'GII') return '<span class="badge-gii">GII</span>';
    if (raceClass === 'GI') return '<span class="badge-gi">GI</span>';
    return `<span class="badge-class">${raceClass || '未分類'}</span>`;
}

// 距離ラベル
function getDistanceLabel(distance) {
    if (distance <= 1400) return '<span class="badge-dist sprint">短距離</span>';
    if (distance <= 1800) return '<span class="badge-dist mile">マイル×2</span>';
    if (distance <= 2200) return '<span class="badge-dist middle">中距離</span>';
    return '<span class="badge-dist long">長距離×2</span>';
}

// レース詳細を読み込み
async function loadRaceDetail(raceId) {
    try {
        const res = await fetch(`/api/race/${raceId}`);
        const data = await res.json();

        // レース情報
        document.getElementById('race-title').textContent = data.race_info.name || raceId;
        document.getElementById('race-meta').innerHTML = `
            <span class="badge-class">${data.race_info.class}</span>
            <span>${data.race_info.course} / ${data.race_info.distance}m</span>
            ${data.is_target ? '<span class="badge-target">対象レース</span>' : '<span class="badge-nottarget">対象外</span>'}
        `;

        // 馬テーブル
        renderHorseTable(data.horses);

        // 三連複
        if (data.is_target && data.trio_bets.length > 0) {
            renderTrioBets(data.trio_bets, data.summary);
            document.getElementById('trio-section').style.display = 'block';
        } else {
            document.getElementById('trio-section').style.display = 'none';
        }

        document.getElementById('race-detail').style.display = 'block';

    } catch (err) {
        console.error('Error loading race detail:', err);
    }
}

// 馬テーブル描画
function renderHorseTable(horses) {
    const tbody = document.getElementById('horse-list');
    tbody.innerHTML = '';

    horses.forEach(h => {
        const winEv = h.win_ev || 0;
        const placeEv = h.place_ev || 0;

        let rating = '';
        let ratingClass = '';
        if (h.popularity <= 2) {
            rating = '★ 軸馬候補';
            ratingClass = 'axis';
        } else if (placeEv >= 1.0 && h.odds >= 10 && h.odds <= 50) {
            rating = '◎ 穴馬候補';
            ratingClass = 'hole';
        } else if (winEv >= 1.2) {
            rating = '○ 妙味あり';
            ratingClass = 'good';
        } else {
            rating = '-';
            ratingClass = 'normal';
        }

        const tr = document.createElement('tr');
        tr.className = ratingClass;
        tr.innerHTML = `
            <td><span class="badge">${h.num}</span></td>
            <td class="horse-name">${h.name}</td>
            <td>${h.odds?.toFixed(1) || '-'}</td>
            <td>${((h.estimated_prob || 0) * 100).toFixed(1)}%</td>
            <td class="${winEv >= 1.0 ? 'ev-high' : ''}">${winEv.toFixed(2)}</td>
            <td class="${placeEv >= 1.0 ? 'ev-high' : ''}">${placeEv.toFixed(2)}</td>
            <td class="rating">${rating}</td>
        `;
        tbody.appendChild(tr);
    });
}

// 三連複買い目描画
function renderTrioBets(bets, summary) {
    // サマリー
    const summaryEl = document.getElementById('trio-summary');
    summaryEl.innerHTML = `
        <div class="summary-grid">
            <div class="summary-item">
                <span class="label">軸馬</span>
                <span class="value">${summary.axis_horse?.num} ${summary.axis_horse?.name}</span>
            </div>
            <div class="summary-item">
                <span class="label">穴馬</span>
                <span class="value">${summary.hole_horses?.join(', ')}</span>
            </div>
            <div class="summary-item">
                <span class="label">買い目数</span>
                <span class="value">${summary.total_bets}点</span>
            </div>
            <div class="summary-item">
                <span class="label">合計投資</span>
                <span class="value highlight">${summary.total_investment?.toLocaleString()}円</span>
            </div>
        </div>
    `;

    // 買い目リスト
    const listEl = document.getElementById('trio-list');
    listEl.innerHTML = '';

    bets.forEach(bet => {
        const div = document.createElement('div');
        div.className = `trio-item ${bet.is_boosted ? 'boosted' : ''}`;

        const horseNames = bet.horses.map(h => h.name).join(' × ');
        const combo = bet.combo.join('-');

        div.innerHTML = `
            <div class="trio-combo">${combo}</div>
            <div class="trio-horses">${horseNames}</div>
            <div class="trio-amount">${bet.amount}円</div>
            ${bet.multipliers.length > 0 ? `<div class="trio-mult">${bet.multipliers.join(' ')}</div>` : ''}
        `;

        listEl.appendChild(div);
    });
}

// 初期化
document.addEventListener('DOMContentLoaded', loadTodayRaces);
