/* Chart.js plus accessible linked data tables. No chart is the only navigation. */
(() => {
  'use strict';
  const el=(tag,cls,text)=>{const item=document.createElement(tag);if(cls)item.className=cls;if(text!=null)item.textContent=text;return item;};
  document.querySelectorAll('[data-insights]').forEach(section=>{
    let charts=[],controller;
    const token = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const palette = () => ['--ui-primary','--ui-success','--ui-warning','--ui-accent','--ui-muted','--ui-danger'].map(name=>token(name)||'CanvasText');
    function syncChartTheme(chart){
      const ink=token('--ui-muted')||'CanvasText',line=token('--ui-line')||'GrayText';
      chart.options.plugins.legend.labels.color=ink;
      const colors=palette(),accent=colors[charts.indexOf(chart)%2===1?1:0];
      chart.data.datasets.forEach(dataset=>{
        dataset.borderColor=accent;
        dataset.backgroundColor=chart.config.type==='line'?(/^#[\da-f]{6}$/i.test(accent)?accent+'1a':'transparent'):colors;
      });
      Object.values(chart.options.scales||{}).forEach(axis=>{
        if(axis.ticks)axis.ticks.color=ink;
        if(axis.grid)axis.grid.color=line;
      });
    }
    document.addEventListener('docodive:themechange',()=>charts.forEach(chart=>{syncChartTheme(chart);chart.update('none');}));
    const status=section.querySelector('.insights-status'),grid=section.querySelector('.insights-charts'),cards=section.querySelector('.insights-cards'),retry=section.querySelector('.insights-retry');
    async function load(){
      controller?.abort();controller=new AbortController();
      charts.forEach(c=>c.destroy());charts=[];grid.replaceChildren();cards.replaceChildren();grid.setAttribute('aria-busy','true');
      status.textContent='Loading insights…';retry.hidden=true;
      try{
        if(!navigator.onLine)throw Error('You are offline. Reconnect to load insights.');
        const response=await fetch('/admin-studio/api/insights?kind='+encodeURIComponent(section.dataset.insights)+'&days='+section.querySelector('select').value,{signal:controller.signal});
        if(response.redirected||response.status===401||response.status===403){status.replaceChildren(el('span',null,'Your session has expired. '));const link=el('a',null,'Sign in again');link.href='/admin-studio/login';status.append(link);return;}
        if(!response.ok)throw Error('Insights could not be loaded. Please retry.');
        const data=await response.json();
        for(const item of data.charts){
          const panel=el('article','studio-panel insight-chart');panel.append(el('h3','h6',item.title));
          if(!item.values.length||!item.values.some(v=>v>0)){panel.append(el('p','studio-chart-empty','No recorded data for this period.'));grid.append(panel);continue;}
          const figure=el('div','insight-canvas'),canvas=el('canvas');canvas.setAttribute('role','img');canvas.setAttribute('aria-label',item.title+'. Exact values and links are in the table below.');figure.append(canvas);panel.append(figure);
          const details=el('details','insight-data');details.append(el('summary',null,'View data & open records'));const table=el('table','table table-sm'),tbody=el('tbody');
          item.labels.forEach((label,i)=>{const row=el('tr'),cell=el('th');cell.scope='row';const link=el('a',null,label);link.href=item.links[i];cell.append(link);row.append(cell,el('td',null,item.values[i].toLocaleString()));tbody.append(row);});table.append(tbody);details.append(table);panel.append(details);grid.append(panel);
          if(window.Chart){const colors=palette();const chartColor=colors[charts.length%2?1:0];charts.push(new Chart(canvas,{type:item.type,data:{labels:item.labels,datasets:[{label:item.title,data:item.values,backgroundColor:item.type==='line'?'transparent':colors,borderColor:chartColor,borderWidth:2,tension:.3,fill:item.type==='line',pointRadius:2,pointHoverRadius:5}]},options:{responsive:true,maintainAspectRatio:false,animation:matchMedia('(prefers-reduced-motion: reduce)').matches?false:{duration:250},plugins:{legend:{display:item.type==='doughnut',labels:{font:{size:10},boxWidth:10}}},onClick:(_,active)=>{if(active[0])location.href=item.links[active[0].index];},scales:item.type==='doughnut'?{}:{x:{grid:{display:false},ticks:{font:{size:9},maxRotation:0}},y:{beginAtZero:true,grid:{color:token('--ui-line')},border:{display:false},ticks:{precision:0,font:{size:9}}}}}}));}else{figure.remove();details.open=true;}
        }
        charts.forEach(chart=>{syncChartTheme(chart);chart.update('none');});
        const icons=['people','book','patch-check','person-dash','activity','star','chat-square-text','lightbulb'];data.cards.forEach((card,index)=>{const link=el('a','studio-stat');link.href=card.url;const icon=el('i','bi bi-'+(icons[index]||'bar-chart')+' studio-stat-icon');icon.setAttribute('aria-hidden','true');link.append(el('span',null,card.label),el('strong',null,card.value.toLocaleString()),icon);cards.append(link);});cards.setAttribute('aria-busy','false');
        section.querySelector('.insights-note').textContent=data.note;
        status.textContent=window.Chart?'Updated. Select a chart segment to explore records.':'Chart library unavailable. Exact data and navigation are available in the tables.';
      }catch(error){if(error.name==='AbortError')return;status.textContent=error.message;retry.hidden=false;}
      finally{grid.setAttribute('aria-busy','false');cards.setAttribute('aria-busy','false');}
    }
    section.querySelector('select').addEventListener('change',load);retry.addEventListener('click',load);load();
  });
})();
