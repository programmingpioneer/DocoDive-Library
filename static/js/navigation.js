/* Bootstrap owns menu state; desktop hover is a small, cancellable convenience. */
(() => {
  'use strict';
  function setup() {
    if(!window.bootstrap)return;
    const api=window.bootstrap.Dropdown;
    const triggers=[...document.querySelectorAll('.navbar [data-bs-toggle="dropdown"]')];
    document.addEventListener('show.bs.dropdown',event=>{
      if(!triggers.includes(event.target))return;
      triggers.forEach(trigger=>{if(trigger!==event.target&&trigger.getAttribute('aria-expanded')==='true')api.getOrCreateInstance(trigger).hide();});
    });
    for(const id of ['learningDropdown','communityDropdown']){
      const trigger=document.getElementById(id);if(!trigger)continue;
      const parent=trigger.closest('.dropdown'),dropdown=api.getOrCreateInstance(trigger);
      let showTimer,hideTimer,openedByHover=false;
      const cancel=()=>{clearTimeout(showTimer);clearTimeout(hideTimer);};
      parent.addEventListener('mouseenter',()=>{
        cancel();if(!matchMedia('(hover:hover) and (min-width:992px)').matches)return;
        showTimer=setTimeout(()=>{if(trigger.getAttribute('aria-expanded')==='true')return;dropdown.show();openedByHover=true;},120);
      });
      parent.addEventListener('mouseleave',()=>{
        cancel();if(!matchMedia('(hover:hover) and (min-width:992px)').matches)return;
        hideTimer=setTimeout(()=>{if(!parent.contains(document.activeElement)||(openedByHover&&document.activeElement===trigger)){dropdown.hide();openedByHover=false;}},160);
      });
      parent.addEventListener('focusout',()=>{hideTimer=setTimeout(()=>{if(!parent.contains(document.activeElement))dropdown.hide();},0);});
      trigger.addEventListener('click',()=>{cancel();openedByHover=false;});
      trigger.addEventListener('keydown',event=>{
        cancel();openedByHover=false;if(event.key==='Enter'||event.key===' '){event.preventDefault();dropdown.toggle();}
      });
      parent.addEventListener('keydown',event=>{openedByHover=false;if(event.key==='Escape')cancel();});
    }
  }
  if(document.readyState==='complete')setup();else document.addEventListener('DOMContentLoaded',setup,{once:true});
})();
