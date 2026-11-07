/* Apply a saved appearance choice, or Light, before the document is painted. */
(() => {
  'use strict';
  let choice='light';
  try{const saved=window.localStorage.getItem('docodive_theme');if(saved==='light'||saved==='dark')choice=saved;}catch(error){}
  const dark=choice==='dark';
  const root=document.documentElement;
  root.dataset.themeChoice=choice;root.dataset.bsTheme=dark?'dark':'light';root.style.colorScheme=dark?'dark':'light';
})();
