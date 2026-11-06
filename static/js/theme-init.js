/* Apply a valid local appearance choice before the document is painted. */
(() => {
  'use strict';
  let choice='system';
  try{const saved=window.localStorage.getItem('docodive_theme');if(saved==='light'||saved==='dark')choice=saved;}catch(error){}
  const dark=choice==='dark'||(choice==='system'&&typeof window.matchMedia==='function'&&window.matchMedia('(prefers-color-scheme: dark)').matches);
  const root=document.documentElement;
  root.dataset.themeChoice=choice;root.dataset.bsTheme=dark?'dark':'light';root.style.colorScheme=dark?'dark':'light';
})();
