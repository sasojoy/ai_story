/* 公開的傳（/zhuan/<代碼>，tianxia/features/zhuan/zhuan_html.py 生成的頁）：直書切換與分享。
 * 只給那一頁載（不宣告進包的 web，/ 不載）。CSP（第 213 批）不准 inline 的程式，從頁裡的 <script> 原樣搬出來。
 */
(function(){
  var KEY="tx-zhuan-vertical",text=document.querySelector(".zh-text"),btn=document.getElementById("vert");
  function set(on){text.classList.toggle("vertical",on);btn.setAttribute("aria-pressed",on?"true":"false");}
  try{set(localStorage.getItem(KEY)==="1");}catch(e){}
  document.addEventListener("click",function(){document.body.classList.add("zh-skip");},true);
  btn.addEventListener("click",function(){var on=!text.classList.contains("vertical");set(on);try{localStorage.setItem(KEY,on?"1":"0");}catch(e){}});
  function toast(msg){var d=document.createElement("div");d.className="toast";d.textContent=msg;document.body.appendChild(d);setTimeout(function(){d.remove();},2200);}
  document.getElementById("share").addEventListener("click",function(){
    var url=location.href.split("#")[0],title=document.title;
    if(navigator.share){navigator.share({title:title,url:url}).catch(function(){});return;}
    if(navigator.clipboard){navigator.clipboard.writeText(url).then(function(){toast("網址已複製");},function(){prompt("複製這個網址",url);});}
    else prompt("複製這個網址",url);
  });
})();
