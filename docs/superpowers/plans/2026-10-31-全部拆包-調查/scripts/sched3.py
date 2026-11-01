import sys,io,json
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
# 編號: (名稱, 方法, 行, 類型, 額外小時)
B={
2:('出陣約戰',34,683,'move',0),3:('走一趟',12,200,'move',0),4:('探索一顆',15,283,'move',0),
5:('決戰看',31,705,'move',0),6:('決戰打a',14,201,'move',0),7:('決戰打b',29,466,'move',0),8:('決戰打c',19,345,'move',0),
10:('酒肆',43,718,'move',0),11:('核心收接縫',0,0,'core',2),12:('單挑',36,611,'move',1),
13:('拿掉一',18,337,'drop',3),14:('拿掉二',0,0,'drop',1),15:('共用規則層登記',0,0,'reg',0),16:('事件檢定進核心',18,372,'core',0),
17:('出陣三',15,208,'move',0),18:('探索三',9,107,'move',0),19:('人物情誼一',29,257,'move',1),20:('人物情誼二',30,516,'move',1),
21:('交友求見',31,305,'move',0),22:('引導一',31,444,'move',0),23:('修練',32,294,'move',0),24:('有所感與頓悟',10,101,'move',1),
25:('世界層掛鉤',0,0,'core',1),26:('事件機制',0,0,'core',1),27:('玉璽一',13,380,'move',1),28:('玉璽二',22,436,'move',0),
29:('列傳',20,219,'move',1),30:('一條線＋簽到',13,126,'move',0),31:('大勢人物',24,388,'move',0),32:('效果與叛投掛鉤',0,0,'core',0),
33:('軍情一',17,280,'move',0),34:('軍情二',5,85,'move',2),35:('陣營',20,252,'move',0),36:('本週卡殼化',0,0,'core',-1),
37:('玩家互動一',31,365,'move',0),38:('玩家互動二',28,435,'move',0),39:('體力玩法＋閉關',10,240,'move',0),40:('世界模型第二批',0,0,'reg',1),
41:('鐵匠鋪',23,381,'move',0),42:('裝備',13,128,'move',0),43:('銀兩出口',17,225,'move',0),44:('煉製與自創',16,126,'move',1),
45:('懸賞榜',4,86,'move',3),46:('地盤',27,431,'move',1),47:('移動一',19,208,'move',0),48:('移動二',15,307,'move',0),
49:('輿圖一',11,82,'move',2),50:('輿圖二',0,0,'split',0),51:('玉璽三',0,0,'split',0),52:('戰記',0,0,'move',3),
53:('手機通知',0,0,'move',2),54:('決戰收尾',0,0,'split',1),55:('補算換季收接縫',11,500,'core',1),56:('選單收接縫',9,369,'core',0),
57:('分派收接縫',5,445,'core',1),58:('商城收尾',12,24,'move',0),59:('引導二',1,9,'move',3),60:('假人殼收尾',0,0,'core',-1),
61:('混合測試檔歸位',0,0,'tests',0),62:('內容一',0,0,'content',0),63:('內容二',0,0,'content',1),
64:('網頁一',0,1345,'web',1),65:('網頁二',0,600,'web',0),66:('網頁三',0,900,'web',1),67:('網頁四',0,1867,'web',1),
68:('伺服器一',0,0,'server',0),69:('伺服器二',0,0,'server',1),
}
def hours(t,l,x):
    h={'move':5.5+l/150,'core':9,'reg':6,'drop':8,'split':7,'content':7,'web':7+l/600,'server':8,'tests':8}[t]
    return round(h+x,1)
H={k:hours(v[3],v[2],v[4]) for k,v in B.items()}
seq=sum(H.values())
print('remaining batches',len(B),'(第2批起，含進行中的第2批)')
print('sequential hours',round(seq,1))
for lo,hi in [(2,12),(13,40),(41,54),(55,61),(62,69)]:
    print(lo,hi,round(sum(H[k] for k in H if lo<=k<=hi),1))
# 兩條並行：配對（第二條多 1.5 小時：合 develop 進來、重跑 Task 1 與前後對照）
pairs=[(3,None)]  # 六包照舊一次一批
P=[(17,19),(18,22),(20,23),(21,24),(27,29),(28,30),(31,37),(33,38),(34,39),(35,41),(46,42),(47,43),(48,44),(49,45),(50,51),(54,None),(58,59),(65,68),(66,69)]
paired=set(x for p in P for x in p if x)
slots=[]
for k in sorted(H):
    if k<13: slots.append(H[k]); continue
    if k in paired: continue
    slots.append(H[k])
for a,b in P:
    if b is None: slots.append(H[a]); continue
    slots.append(max(H[a],H[b])+1.5)
par=sum(slots)
print('parallel hours',round(par,1),'slots',len(slots))
for d in (9,10):
    print(f'@{d}h/day sequential days',round(seq/d,1),'parallel days',round(par/d,1))
json.dump(H,open(r'C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\split\tmp_check\hours_fixed.json','w'),ensure_ascii=False)
for k in sorted(H): print(k,B[k][0],H[k])

