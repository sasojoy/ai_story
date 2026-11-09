/* 戰記頁（/zhanji/<代碼>，tianxia/features/tale/tale_html.py 生成的頁）：分享與遊戲裡那一層的「返回」。
 * 只給那一頁載（不宣告進包的 web，/ 不載）。CSP（第 213 批）不准 inline 的程式，從頁裡的 <script> 原樣搬出來。
 */
(function(){
  function toast(msg){var d=document.createElement("div");d.className="zj-toast";d.textContent=msg;document.body.appendChild(d);setTimeout(function(){d.remove();},2200);}
  var share=document.getElementById("zj-share"),back=document.getElementById("zj-back");
  if(share)share.addEventListener("click",function(){
    var url=share.getAttribute("data-url"),title=document.title;
    if(navigator.share){navigator.share({title:title,url:url}).catch(function(){});return;}
    if(navigator.clipboard){navigator.clipboard.writeText(url).then(function(){toast("網址已複製");},function(){prompt("複製這個網址",url);});}
    else prompt("複製這個網址",url);
  });
  if(back)back.addEventListener("click",function(){try{parent.postMessage({zhanji:"close"},location.origin);}catch(e){}});
})();
