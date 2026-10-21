# -*- coding: utf-8 -*-
"""Scale every recipe to a 500 g edible portion and add more dishes."""
from __future__ import annotations

import re

import xlrd
import xlwt

FOODS_PATH = r"C:\Tube\Health-ing\Foods.xls"
RECIPE_PATH = r"C:\Tube\Health-ing\Recipe.xls"
TARGET = 500

FISH = {
    "鯉魚", "鯽魚", "鱸魚", "草魚", "鰱魚", "青魚", "帶魚", "黃魚", "鯖魚", "鮪魚",
    "鮭魚", "鱈魚", "鯛魚", "秋刀魚", "沙丁魚", "鰻魚", "鱔魚", "泥鰍", "虱目魚",
    "石斑魚", "比目魚", "鯊魚", "白鯧", "烏魚", "鰹魚", "吳郭魚",
}
CRUSTACEAN = {"蝦", "蝦米", "龍蝦", "螃蟹"}
MOLLUSC = {
    "蛤蜊", "牡蠣", "蜆", "淡菜", "干貝", "鮑魚", "章魚", "魷魚", "烏賊",
    "海蜇", "田螺", "蟶子", "海參", "海膽",
}
EGG = {"雞蛋", "蛋白", "蛋黃", "鴨蛋", "皮蛋", "鵪鶉蛋"}
MILK = {"牛奶", "羊奶", "奶油", "起司", "優格"}
GLUTEN = {"小麥", "大麥", "燕麥"}
SOY = {"黃豆", "黑豆", "豆腐", "豆漿", "豆干", "腐竹", "納豆", "醬油", "毛豆", "黃豆芽"}
PEANUT = {"花生", "花生油"}
NUT = {"杏仁果", "腰果", "夏威夷豆", "核桃", "松子", "栗子", "甜杏仁", "北杏仁", "白果"}
SEED = {"黑芝麻", "白芝麻", "麻油", "南瓜子", "葵花子", "亞麻仁"}
OTHER = {"蕎麥", "芹菜", "西洋芹", "芥末", "芥菜", "山葵", "醋", "黃酒"}
ALLERGENS = FISH | CRUSTACEAN | MOLLUSC | EGG | MILK | GLUTEN | SOY | PEANUT | NUT | SEED | OTHER

# Additional well-known dishes. Parts are relative and later scaled to 500 g.
NEW = r"""
China|蛋炒飯|Egg fried rice|チャーハン|계란볶음밥|粳米 260,雞蛋 80,蔥 25,胡蘿蔔 30,豌豆 30,醬油 15,食鹽 6,花生油 12
China|番茄炒蛋|Tomato and egg|トマトと卵|토마토달걀볶음|雞蛋 180,番茄 220,蔥 20,食鹽 8,白糖 8,花生油 16
China|麻婆豆腐|Mapo tofu|麻婆豆腐|마파두부|豆腐 220,豬肉 90,辣椒 25,花椒 10,大蒜 12,生薑 10,蔥 12,醬油 16,食鹽 6
China|宮保雞丁|Kung pao chicken|宮保鶏丁|궁바오치킨|雞肉 180,花生 60,辣椒 30,蔥 25,生薑 12,大蒜 12,醬油 16,醋 12,食鹽 6,白糖 10
China|糖醋排骨|Sweet and sour ribs|酢豚スペアリブ|탕수갈비|豬肉 240,醋 30,白糖 25,醬油 20,生薑 12,蔥 15,食鹽 6,小麥 12
China|清蒸鱸魚|Steamed sea bass|清蒸スズキ|찐농어|鱸魚 320,生薑 25,蔥 30,醬油 20,食鹽 8,麻油 8
China|水餃|Pork dumplings|水餃子|물만두|小麥 180,豬肉 160,高麗菜 80,蔥 25,生薑 12,醬油 16,麻油 8,食鹽 8
China|小籠包|Soup dumplings|小籠包|샤오롱바오|小麥 180,豬肉 200,生薑 15,蔥 20,醬油 18,食鹽 8,麻油 10
China|紅燒肉|Red-braised pork|紅焼肉|홍샤오러우|豬肉 300,醬油 30,冰糖 20,生薑 15,蔥 20,黃酒 15,食鹽 6,八角 6
China|魚香茄子|Fish-fragrant eggplant|魚香茄子|어향가지|茄子 240,豬肉 60,大蒜 16,生薑 12,蔥 16,醬油 16,醋 16,白糖 12,食鹽 6
China|青椒肉絲|Pork with green pepper|青椒肉絲|청피육사|豬肉 160,青椒 160,竹筍 40,醬油 16,食鹽 8,生薑 8,蔥 12
China|酸辣湯|Hot and sour soup|酸辣湯|산라탕|豆腐 80,豬肉 50,竹筍 40,黑木耳 30,雞蛋 50,醋 30,胡椒 8,醬油 16,食鹽 8,香菇 20
China|回鍋肉|Twice-cooked pork|回鍋肉|회과육|豬肉 220,青椒 80,大蒜 16,生薑 12,豆干 40,醬油 16,食鹽 6
China|涼拌黃瓜|Smashed cucumber|拍黃瓜|오이무침|黃瓜 360,大蒜 20,醋 25,醬油 16,麻油 12,食鹽 8,辣椒 10
China|蒜蓉青花菜|Garlic broccoli|ブロッコリー|마늘브로콜리|青花菜 360,大蒜 30,食鹽 8,花生油 16,醬油 8
China|木須肉|Moo shu pork|木須肉|무수육|豬肉 140,雞蛋 80,黑木耳 40,黃瓜 60,竹筍 40,醬油 16,蔥 16,食鹽 8
China|蛋花湯|Egg drop soup|卵スープ|계란국|雞蛋 120,蔥 20,食鹽 10,香菇 40,豆腐 60,番茄 30
China|白切雞|Poached chicken|白切鶏|백절계|雞肉 360,生薑 25,蔥 30,食鹽 12,麻油 10,醬油 12
China|糖醋魚|Sweet and sour fish|糖醋魚|탕수어|鱸魚 280,醋 30,白糖 25,生薑 12,蔥 15,醬油 12,食鹽 6,小麥 10
China|火鍋拼盤|Hot pot platter|火鍋|훠궈|牛肉 80,羊肉 60,豆腐 50,高麗菜 50,金針菇 30,海帶 25,蝦 40,茼蒿 30,醬油 12,食鹽 8,辣椒 10,白芝麻 8
China|番茄牛腩|Tomato beef brisket|トマト牛筋煮|토마토우둔찜|牛肉 200,番茄 120,馬鈴薯 60,洋蔥 25,生薑 10,食鹽 8,醬油 12
China|乾煸四季豆|Dry-fried green beans|いんげん炒め|마른강낭콩볶음|四季豆 280,豬肉 60,大蒜 16,辣椒 16,食鹽 8,醬油 10
China|蒜蓉芥藍|Garlic Chinese broccoli|カイラン|마늘카이란|芥藍 360,大蒜 30,食鹽 8,花生油 16,醬油 8
China|紅燒獅子頭|Braised pork meatballs|獅子頭|사자두|豬肉 240,高麗菜 80,生薑 12,蔥 16,醬油 20,食鹽 8,雞蛋 16,小麥 12
Taiwan|滷肉飯|Braised pork rice|魯肉飯|루로우판|粳米 240,豬肉 140,醬油 28,蔥 16,大蒜 12,食鹽 6,雞蛋 30,辣椒 8
Taiwan|三杯雞|Three-cup chicken|三杯鶏|삼배계|雞肉 280,羅勒 25,生薑 20,大蒜 20,醬油 25,麻油 20,食鹽 6,辣椒 8
Taiwan|蚵仔煎|Oyster omelette|牡蠣オムレツ|굴전|牡蠣 180,雞蛋 100,小麥 40,青江菜 50,食鹽 8,醬油 12,辣椒 8
Taiwan|薑母鴨|Ginger duck|薑母鴨|생강오리탕|鴨肉 320,生薑 60,黃酒 30,食鹽 8,枸杞 12,紅棗 16
Taiwan|鹽酥雞|Popcorn chicken|塩酥鶏|옌수지|雞肉 280,小麥 40,羅勒 20,大蒜 16,辣椒 16,食鹽 10,胡椒 8,花椒 6
Taiwan|擔仔麵|Danzai noodles|担仔麺|단짜이면|小麥 200,豬肉 80,蝦 40,大蒜 16,醋 16,香菜 16,食鹽 8,醬油 12
Taiwan|刈包|Gua bao|割包|괄바오|小麥 200,豬肉 150,花生 40,香菜 25,高麗菜 40,食鹽 8,白糖 10
Taiwan|肉粽|Rice dumpling|粽|쫑즈|糯米 240,豬肉 80,香菇 30,蝦米 20,花生 30,食鹽 8,醬油 16,蛋黃 12
Taiwan|皮蛋豆腐|Century egg tofu|ピータン豆腐|피단두부|皮蛋 120,豆腐 220,醬油 16,麻油 12,蔥 16,食鹽 6,辣椒 8
Taiwan|炒米粉|Stir-fried rice vermicelli|ビーフン|쌀국수볶음|粳米 220,豬肉 60,蝦 40,高麗菜 50,香菇 25,胡蘿蔔 25,醬油 16,食鹽 6,蔥 12
Taiwan|茶葉蛋|Tea eggs|茶葉蛋|차예단|雞蛋 300,紅茶 20,醬油 30,食鹽 8,八角 8,生薑 10
Taiwan|客家小炒|Hakka stir-fry|客家炒め|하카볶음|豬肉 80,魷魚 60,豆干 70,芹菜 50,辣椒 16,洋蔥 20,食鹽 8,醬油 12
Taiwan|皮蛋瘦肉粥|Congee with pork|皮蛋肉粥|피단죽|粳米 200,豬肉 60,皮蛋 80,生薑 10,蔥 12,食鹽 8,香菜 8
Hong Kong|雲吞麵|Wonton noodles|ワンタン麺|완탕면|小麥 200,豬肉 80,蝦 50,蔥 16,生薑 10,醬油 16,食鹽 8,麻油 8,青江菜 40
Hong Kong|乾炒牛河|Beef chow fun|牛肉河粉|건차우펀|牛肉 140,粳米 200,黃豆芽 50,蔥 20,醬油 18,食鹽 6,生薑 8
Hong Kong|叉燒飯|Char siu rice|叉焼飯|차슈덮밥|豬肉 160,粳米 220,蜂蜜 20,醬油 24,生薑 8,大蒜 8,食鹽 6
Hong Kong|絲襪奶茶|Hong Kong milk tea|ミルクティー|홍콩밀크티|紅茶 30,牛奶 420,白糖 40
Hong Kong|蛋撻|Egg tart|エッグタルト|에그타르트|小麥 140,奶油 60,雞蛋 80,牛奶 120,白糖 50,食鹽 4
Hong Kong|燒味飯|Roast meat rice|焼味飯|구운고기덮밥|豬肉 100,鴨肉 80,粳米 220,黃瓜 30,醬油 16,食鹽 6,蜂蜜 10
Macau|葡式蛋撻|Portuguese egg tart|ポルトガル式タルト|포르투갈 에그타르트|小麥 130,奶油 50,雞蛋 90,牛奶 140,白糖 50,食鹽 4,肉桂 4
Macau|豬扒包|Pork chop bun|ポークチョップパン|돈가스번|豬肉 180,小麥 160,番茄 30,洋蔥 20,食鹽 8,醬油 12,胡椒 6
Japan|拉麵|Ramen|ラーメン|라멘|小麥 180,豬肉 80,雞蛋 50,蔥 25,海帶 20,醬油 20,生薑 10,食鹽 8,竹筍 20
Japan|天婦羅|Tempura|天ぷら|덴푸라|蝦 140,地瓜 60,茄子 40,小麥 80,雞蛋 30,食鹽 8,白蘿蔔 30,生薑 8,醬油 12
Japan|味噌湯|Miso soup|味噌汁|된장국|豆腐 180,海帶 40,蔥 30,黃豆 80,食鹽 10,香菇 20
Japan|豬排丼|Pork cutlet bowl|カツ丼|가츠동|豬肉 160,粳米 200,雞蛋 50,洋蔥 30,小麥 20,醬油 12,食鹽 6,蔥 8
Japan|牛丼|Beef rice bowl|牛丼|규동|牛肉 160,粳米 220,洋蔥 50,醬油 16,食鹽 6,生薑 8,蔥 8
Japan|壽喜燒|Sukiyaki|すき焼き|스키야키|牛肉 180,豆腐 60,高麗菜 40,蔥 25,香菇 20,金針菇 20,醬油 16,白糖 12,食鹽 6,雞蛋 20
Japan|炸豬排|Tonkatsu|とんかつ|돈카츠|豬肉 220,小麥 50,雞蛋 40,高麗菜 80,食鹽 8,醬油 12,白蘿蔔 16
Japan|日式咖哩飯|Japanese curry rice|カレーライス|카레라이스|粳米 200,牛肉 80,馬鈴薯 60,胡蘿蔔 40,洋蔥 40,薑黃 8,醬油 12,食鹽 6,蘋果 10
Japan|親子丼|Chicken and egg bowl|親子丼|오야코동|雞肉 140,雞蛋 80,粳米 200,洋蔥 30,醬油 12,食鹽 6,蔥 8
Japan|烤雞串|Yakitori|焼き鳥|야키토리|雞肉 320,蔥 40,醬油 24,白糖 12,食鹽 6,生薑 8
Japan|大阪燒|Okonomiyaki|お好み焼き|오코노미야키|小麥 80,高麗菜 180,雞蛋 60,豬肉 50,蔥 16,醬油 12,食鹽 6,紫菜 12
Japan|烏龍麵|Udon|うどん|우동|小麥 220,蔥 25,豆腐 40,海帶 20,醬油 16,食鹽 8,雞蛋 20,香菇 16
Japan|蕎麥麵|Soba|そば|소바|蕎麥 240,蔥 25,海帶 20,醬油 16,食鹽 8,生薑 8,雞蛋 16
Japan|飯糰|Rice ball|おにぎり|주먹밥|粳米 400,紫菜 20,食鹽 8,鮭魚 50
Japan|照燒雞|Teriyaki chicken|照り焼き|데리야키치킨|雞肉 280,醬油 30,蜂蜜 20,生薑 12,大蒜 10,食鹽 6,粳米 40
South Korea|泡菜|Kimchi|キムチ|김치|大白菜 320,辣椒 40,大蒜 25,生薑 16,蔥 20,食鹽 16,蝦米 12,白蘿蔔 30
South Korea|烤牛肉|Bulgogi|プルコギ|불고기|牛肉 280,梨 40,洋蔥 30,大蒜 16,生薑 12,醬油 24,麻油 12,白糖 12,食鹽 6,蔥 10
South Korea|烤五花肉|Grilled pork belly|サムギョプサル|삼겹살|豬肉 320,大蒜 20,生菜 40,蔥 20,辣椒 12,食鹽 8,麻油 10,醬油 10
South Korea|辣炒年糕|Spicy rice cakes|トッポッキ|떡볶이|粳米 280,辣椒 30,蔥 25,醬油 20,白糖 12,食鹽 6,高麗菜 40
South Korea|豆腐鍋|Soft tofu stew|スンドゥブ|순두부찌개|豆腐 240,雞蛋 50,豬肉 40,辣椒 20,洋蔥 25,大蒜 12,蔥 16,食鹽 8,醬油 12,蝦 16
South Korea|參雞湯|Ginseng chicken soup|サムゲタン|삼계탕|雞肉 280,糯米 60,紅棗 20,大蒜 20,生薑 12,人參 16,食鹽 10,栗子 16
South Korea|海鮮煎餅|Seafood pancake|チヂミ|해물파전|小麥 80,雞蛋 50,蝦 60,魷魚 40,蔥 40,韭菜 30,食鹽 8,醬油 10
South Korea|紫菜飯包|Kimbap|キンパ|김밥|粳米 220,紫菜 20,雞蛋 40,胡蘿蔔 30,菠菜 25,火腿 30,黃瓜 20,食鹽 6,麻油 8
South Korea|韓式炸雞|Korean fried chicken|ヤンニョムチキン|양념치킨|雞肉 280,小麥 30,辣椒 24,大蒜 16,生薑 10,醬油 16,蜂蜜 12,食鹽 8,白糖 10
South Korea|雜菜|Japchae|チャプチェ|잡채|地瓜 80,菠菜 40,胡蘿蔔 40,香菇 30,牛肉 50,洋蔥 25,醬油 16,麻油 12,食鹽 6,白糖 8
South Korea|泡菜鍋|Kimchi stew|キムチチゲ|김치찌개|大白菜 180,豬肉 80,豆腐 60,洋蔥 25,辣椒 20,大蒜 12,蔥 12,食鹽 6,醬油 10
Thailand|打拋豬|Holy basil pork|ガパオ|팟까파오|豬肉 200,羅勒 30,辣椒 25,大蒜 16,洋蔥 20,醬油 16,食鹽 6,雞蛋 40,粳米 80
Thailand|泰式炒河粉|Pad thai|パッタイ|팟타이|粳米 180,蝦 70,雞蛋 50,黃豆芽 40,花生 25,檸檬 20,蔥 16,醬油 16,食鹽 6,白糖 8,辣椒 8
Thailand|青咖哩雞|Green curry chicken|グリーンカレー|그린커리|雞肉 160,椰子汁 140,茄子 40,羅勒 16,辣椒 16,香茅 12,大蒜 10,食鹽 6,薑黃 6,粳米 40
Thailand|芒果糯米飯|Mango sticky rice|マンゴーもち米|망고찹쌀|糯米 220,芒果 180,椰子汁 70,食鹽 4,白糖 12
Thailand|涼拌青木瓜|Green papaya salad|ソムタム|솜땀|木瓜 280,番茄 40,花生 25,辣椒 20,大蒜 12,檸檬 25,醬油 12,食鹽 6
Thailand|泰式炒飯|Thai fried rice|カオパット|카오팟|粳米 240,雞蛋 50,蝦 40,洋蔥 25,番茄 25,檸檬 16,醬油 12,食鹽 6,蔥 10,辣椒 8
Thailand|椰汁雞湯|Chicken coconut soup|トムカーガイ|똠카가이|雞肉 140,椰子汁 180,香茅 20,辣椒 12,檸檬 25,洋菇 25,洋蔥 16,食鹽 6,香菜 10,生薑 8
Thailand|泰式炒空心菜|Stir-fried water spinach|空心菜炒め|공심채볶음|空心菜 320,大蒜 25,辣椒 20,醬油 16,食鹽 8,花生油 16
Vietnam|越南三明治|Banh mi|バインミー|반미|小麥 160,豬肉 80,黃瓜 40,胡蘿蔔 30,香菜 20,辣椒 12,醬油 12,食鹽 6,白蘿蔔 20
Vietnam|炸春捲|Fried spring rolls|春巻き|춘권|小麥 80,豬肉 80,蝦 40,胡蘿蔔 30,黑木耳 20,洋蔥 16,食鹽 6,胡椒 6,生菜 30
Vietnam|焦糖魚|Caramel fish|カーコー|카코|石斑魚 260,白糖 20,醬油 16,蔥 16,辣椒 12,食鹽 6,生薑 8,粳米 40
Vietnam|碎豬肉飯|Broken rice with pork|コムタム|껌땀|粳米 220,豬肉 100,雞蛋 40,黃瓜 30,番茄 25,蔥 12,食鹽 6,醬油 10
Vietnam|青木瓜沙拉|Papaya salad|青パパイヤ|청파파야샐러드|木瓜 260,胡蘿蔔 40,香菜 20,花生 25,檸檬 25,辣椒 12,食鹽 6,蝦 20
India|奶油雞|Butter chicken|バターチキン|버터치킨|雞肉 200,番茄 80,洋蔥 30,奶油 30,優格 40,生薑 10,大蒜 10,薑黃 8,辣椒 8,食鹽 6,香菜 8
India|扁豆糊|Lentil dal|ダール|달|扁豆 220,番茄 50,洋蔥 30,生薑 12,大蒜 10,薑黃 8,辣椒 8,食鹽 8,香菜 10,奶油 8
India|坦都里烤雞|Tandoori chicken|タンドリーチキン|탄두리치킨|雞肉 280,優格 80,生薑 12,大蒜 12,薑黃 10,辣椒 12,檸檬 20,食鹽 8,香菜 8
India|馬鈴薯花椰菜|Potato and cauliflower|アルーゴビ|알루고비|馬鈴薯 180,花椰菜 140,洋蔥 30,番茄 30,薑黃 8,生薑 8,辣椒 8,食鹽 8,香菜 8
India|菠菜起司|Spinach with cheese|パラックパニール|팔락파니르|菠菜 220,起司 100,洋蔥 25,生薑 8,大蒜 8,薑黃 6,奶油 12,食鹽 6,辣椒 6
India|印度炸餃|Samosa|サモサ|사모사|小麥 140,馬鈴薯 140,豌豆 40,洋蔥 25,生薑 8,辣椒 8,食鹽 6,香菜 8,薑黃 6
India|羊肉咖哩|Lamb curry|ラムカレー|양고기커리|羊肉 200,洋蔥 40,番茄 40,優格 30,生薑 10,大蒜 10,薑黃 8,肉桂 6,食鹽 6,香菜 8
India|檸檬飯|Lemon rice|レモンライス|레몬라이스|粳米 300,檸檬 40,花生 25,薑黃 8,辣椒 8,芥末 6,食鹽 6,香菜 8
Indonesia|沙嗲|Chicken satay|サテ|사테|雞肉 220,花生 50,醬油 16,大蒜 12,生薑 8,辣椒 10,食鹽 6,檸檬 16,蔥 10,粳米 40
Indonesia|仁當牛肉|Beef rendang|ルンダン|렌당|牛肉 220,椰子汁 140,洋蔥 25,大蒜 12,生薑 10,辣椒 12,香茅 10,薑黃 6,食鹽 6
Indonesia|雜菜花生沙拉|Gado-gado|ガドガド|가도가도|高麗菜 60,豆苗 40,豆腐 50,雞蛋 40,馬鈴薯 40,花生 40,黃瓜 30,食鹽 6,辣椒 8,醬油 8
Indonesia|炒麵|Fried noodles|ミーゴレン|미고렝|小麥 200,雞肉 50,蝦 30,高麗菜 40,洋蔥 20,醬油 16,食鹽 6,雞蛋 20,蔥 10
Indonesia|黃薑雞湯|Turmeric chicken soup|ソトアヤム|소토아얌|雞肉 160,粳米 80,薑黃 10,香茅 12,洋蔥 20,芹菜 16,食鹽 8,檸檬 16,雞蛋 16
Malaysia|叻沙|Laksa|ラクサ|락사|粳米 160,蝦 60,雞肉 40,椰子汁 80,豆腐 30,黃豆芽 25,雞蛋 25,辣椒 10,香茅 10,食鹽 6,檸檬 8
Malaysia|沙嗲|Satay|サテ|사테|雞肉 220,花生 50,醬油 16,洋蔥 20,辣椒 12,食鹽 6,檸檬 16,黃瓜 20,粳米 30
Malaysia|肉骨茶|Bak kut teh|肉骨茶|바쿠테|豬肉 240,大蒜 25,生薑 12,胡椒 10,醬油 16,食鹽 6,豆腐 30,油菜 20,粳米 30
Malaysia|福建炒麵|Hokkien noodles|福建麺|복건면|小麥 200,蝦 50,豬肉 40,高麗菜 30,醬油 16,食鹽 6,蔥 12,雞蛋 16
Singapore|辣椒螃蟹|Chili crab|チリクラブ|칠리크랩|螃蟹 260,辣椒 30,大蒜 16,生薑 12,番茄 40,雞蛋 30,食鹽 8,白糖 10,蔥 10
Singapore|叻沙|Laksa|ラクサ|락사|粳米 150,蝦 70,椰子汁 90,豆腐 30,黃豆芽 25,雞蛋 25,辣椒 12,香茅 10,食鹽 6
Singapore|炒粿條|Char kway teow|チャークウェイティオ|짜콰이띠아우|粳米 200,蝦 50,雞蛋 40,黃豆芽 40,蔥 16,醬油 16,食鹽 6,豬肉 20
Philippines|酸湯|Sinigang|シニガン|시니강|豬肉 140,白蘿蔔 40,番茄 50,洋蔥 25,菠菜 30,四季豆 25,食鹽 8,檸檬 20,生薑 8
Philippines|烤乳豬|Lechon|レチョン|레촌|豬肉 360,大蒜 20,洋蔥 25,食鹽 12,胡椒 8,月桂葉 8,檸檬 12
Philippines|炒麵|Pancit|パンシット|판싯|小麥 200,雞肉 40,蝦 30,高麗菜 40,胡蘿蔔 25,醬油 16,食鹽 6,檸檬 10,蔥 10
Philippines|西西格|Sisig|シシグ|시시그|豬肉 200,豬肝 40,洋蔥 40,辣椒 20,檸檬 20,食鹽 8,醬油 10,雞蛋 16
Italy|番茄肉醬麵|Spaghetti bolognese|ボロネーゼ|볼로네제|小麥 200,牛肉 100,番茄 80,洋蔥 25,胡蘿蔔 20,大蒜 8,食鹽 6,起司 16,月桂葉 6
Italy|米蘭燉飯|Risotto|リゾット|리소토|粳米 240,洋蔥 30,奶油 30,起司 40,牛肉 30,食鹽 6,黃酒 16,香菇 16
Italy|卡波納拉|Carbonara|カルボナーラ|카르보나라|小麥 240,雞蛋 80,火腿 60,起司 40,胡椒 8,食鹽 6
Italy|千層麵|Lasagna|ラザニア|라자냐|小麥 160,牛肉 80,番茄 70,起司 50,洋蔥 20,牛奶 30,食鹽 6,胡蘿蔔 12
Italy|蔬菜湯|Minestrone|ミネストローネ|미네스트로네|番茄 60,高麗菜 40,胡蘿蔔 30,芹菜 25,洋蔥 20,菜豆 30,馬鈴薯 30,小麥 20,食鹽 8,羅勒 8
Italy|青醬麵|Pesto pasta|ペスト|페스토파스타|小麥 220,羅勒 40,松子 25,起司 30,大蒜 10,食鹽 6,花生油 20
Italy|卡布里沙拉|Caprese salad|カプレーゼ|카프레제|番茄 220,起司 140,羅勒 20,食鹽 8,花生油 12
Italy|海鮮麵|Clam pasta|ボンゴレ|봉골레|小麥 200,蛤蜊 140,大蒜 16,香菜 16,食鹽 6,辣椒 8,檸檬 12,花生油 10
France|紅酒燉雞|Chicken braised with wine|コックオーヴァン|코코뱅|雞肉 220,洋蔥 30,香菇 30,胡蘿蔔 25,月桂葉 8,食鹽 8,百里香 8,黃酒 20,大蒜 8
France|普羅旺斯燉菜|Ratatouille|ラタトゥイユ|라타투이|茄子 120,番茄 100,小黃瓜 80,甜椒 50,洋蔥 30,大蒜 12,羅勒 10,食鹽 8,百里香 6
France|洋蔥湯|French onion soup|オニオンスープ|어니언수프|洋蔥 280,小麥 40,起司 50,奶油 20,食鹽 8,百里香 8,牛肉 16
France|法式鹹派|Quiche|キッシュ|키슈|小麥 140,雞蛋 70,牛奶 80,火腿 50,起司 40,洋蔥 20,食鹽 6,奶油 12
France|馬賽魚湯|Fish stew|ブイヤベース|부야베스|石斑魚 120,蝦 70,淡菜 60,番茄 70,洋蔥 30,大蒜 12,小茴香 8,食鹽 6,薑黃 6
France|可麗餅|Crepe|クレープ|크레이프|小麥 140,雞蛋 60,牛奶 140,奶油 30,白糖 30,食鹽 4,草莓 40
France|法式燉牛肉|Beef stew|ブッフブルギニヨン|소고기스튜|牛肉 220,洋蔥 30,胡蘿蔔 30,香菇 25,馬鈴薯 30,月桂葉 8,食鹽 8,百里香 8,黃酒 16
France|尼斯沙拉|Nicoise salad|ニース風サラダ|니수아즈|鮪魚 120,雞蛋 50,馬鈴薯 50,四季豆 40,番茄 40,油橄欖 20,生菜 30,食鹽 6,檸檬 10
Spain|海鮮飯|Paella|パエリア|파에야|粳米 180,蝦 60,淡菜 40,雞肉 40,甜椒 25,番茄 30,洋蔥 16,食鹽 6,檸檬 12,薑黃 6
Spain|冷湯|Gazpacho|ガスパチョ|가스파초|番茄 300,黃瓜 50,甜椒 30,洋蔥 20,大蒜 10,食鹽 6,花生油 10
Spain|蒜香蝦|Garlic shrimp|アヒージョ|감바스|蝦 280,大蒜 40,辣椒 16,食鹽 8,香菜 16,檸檬 16,花生油 20
Spain|烤章魚|Grilled octopus|タコのガリシア風|문어구이|章魚 300,馬鈴薯 80,食鹽 10,辣椒 12,花生油 12,檸檬 16
Mexico|酪梨醬|Guacamole|ワカモレ|과카몰리|酪梨 280,番茄 50,洋蔥 30,香菜 20,檸檬 25,食鹽 8,辣椒 12
Mexico|起司玉米餅|Quesadilla|ケサディーヤ|케사디야|小麥 160,起司 120,雞肉 50,洋蔥 20,辣椒 10,食鹽 6,香菜 8
Mexico|墨式燉肉|Mexican beef stew|カルネギサダ|멕시칸스튜|牛肉 200,馬鈴薯 60,番茄 40,洋蔥 30,辣椒 16,食鹽 8,香菜 10,玉米 16
Mexico|墨式飯|Mexican rice|メキシカンライス|멕시칸라이스|粳米 240,番茄 60,洋蔥 25,玉米 30,豌豆 25,食鹽 6,辣椒 8,香菜 8
Mexico|辣椒牛肉|Chili con carne|チリコンカン|칠리콘카르네|牛肉 200,菜豆 80,番茄 50,洋蔥 30,辣椒 20,食鹽 8,香菜 8,玉米 10
United States|炸雞|Fried chicken|フライドチキン|후라이드치킨|雞肉 280,小麥 40,食鹽 10,胡椒 8,牛奶 20,雞蛋 16,馬鈴薯 30
United States|蘋果派|Apple pie|アップルパイ|애플파이|蘋果 240,小麥 100,奶油 40,白糖 40,食鹽 4,肉桂 8,檸檬 8
United States|凱薩沙拉|Caesar salad|シーザーサラダ|시저샐러드|生菜 220,雞肉 60,起司 30,小麥 25,雞蛋 20,大蒜 8,食鹽 6,檸檬 10,芥末 6
United States|烤豬肋排|Barbecue ribs|バーベキューリブ|바비큐립|豬肉 300,番茄 40,洋蔥 20,蜂蜜 16,醬油 16,食鹽 8,辣椒 10,黑糖 10
United States|蛤蜊巧達|Clam chowder|クラムチャウダー|클램차우더|蛤蜊 160,馬鈴薯 80,洋蔥 25,芹菜 20,牛奶 80,奶油 16,食鹽 6,胡椒 6
United States|美式鬆餅|Pancakes|パンケーキ|팬케이크|小麥 160,牛奶 140,雞蛋 60,奶油 30,白糖 30,食鹽 4,蜂蜜 20
United Kingdom|牧羊人派|Shepherd's pie|シェパーズパイ|셰퍼드파이|羊肉 180,馬鈴薯 140,洋蔥 25,胡蘿蔔 25,奶油 12,食鹽 8,百里香 6,牛奶 12
United Kingdom|英式早餐|Full breakfast|フルブレックファスト|풀브렉퍼스트|雞蛋 100,火腿 80,豬肉 50,番茄 40,洋菇 30,小麥 40,食鹽 6,奶油 10
United Kingdom|烤牛肉|Roast beef|ローストビーフ|로스트비프|牛肉 260,馬鈴薯 80,胡蘿蔔 30,洋蔥 20,食鹽 8,迷迭香 8,芥末 8
United Kingdom|康沃爾餡餅|Cornish pasty|コーンウォールパイ|콘월파이|小麥 140,牛肉 100,馬鈴薯 80,洋蔥 30,白蘿蔔 30,食鹽 8
Germany|德國香腸|Bratwurst|ブラートヴルスト|브라트부르스트|豬肉 280,小麥 40,食鹽 8,胡椒 6,洋蔥 20,芥末 10,高麗菜 30,馬鈴薯 30
Germany|德式酸菜|Sauerkraut plate|ザワークラウト|사우어크라우트|高麗菜 280,醋 25,豬肉 60,洋蔥 20,食鹽 8,胡椒 6,蘋果 16,芥末 8
Germany|德式炸豬排|Schnitzel|シュニッツェル|슈니첼|豬肉 220,小麥 40,雞蛋 40,馬鈴薯 50,食鹽 8,檸檬 16,奶油 10
Greece|希臘沙拉|Greek salad|ギリシャサラダ|그릭샐러드|番茄 140,黃瓜 100,洋蔥 30,甜椒 30,起司 50,油橄欖 25,食鹽 6,香菜 8
Greece|羊肉串|Souvlaki|スブラキ|수블라키|羊肉 280,洋蔥 30,番茄 30,檸檬 20,食鹽 8,香菜 10,小麥 20,優格 16
Greece|優格黃瓜|Yogurt cucumber dip|ザジキ|차지키|優格 240,黃瓜 140,大蒜 16,食鹽 8,薄荷 12,花生油 10
Greece|菠菜派|Spinach pie|スパナコピタ|스파나코피타|小麥 120,菠菜 160,起司 50,洋蔥 25,雞蛋 30,食鹽 6,奶油 12
Turkey|土耳其燉豆|White bean stew|白いんげん煮|쿠루파술예|菜豆 220,洋蔥 30,番茄 40,羊肉 40,食鹽 8,辣椒 8,香菜 8,檸檬 10
Turkey|皮塔餅|Pita|ピタ|피타|小麥 300,優格 50,番茄 40,黃瓜 30,食鹽 8,油橄欖 12
Turkey|優格黃瓜醬|Cacik|ジャジュク|자즉|優格 240,黃瓜 140,大蒜 16,食鹽 8,薄荷 12,花生油 10
Turkey|土耳其披薩|Pide|ピデ|피데|小麥 180,羊肉 80,洋蔥 30,番茄 40,起司 30,食鹽 6,香菜 10,辣椒 8
Brazil|巴西烤肉|Churrasco|シュハスコ|슈하스코|牛肉 320,食鹽 10,洋蔥 30,辣椒 12,粳米 40,番茄 20
Brazil|海鮮椰汁鍋|Moqueca|モケカ|모케카|石斑魚 160,蝦 60,椰子汁 120,番茄 40,洋蔥 25,辣椒 12,香菜 12,食鹽 8,檸檬 16
Brazil|黑豆飯|Black bean rice|黒豆ご飯|검은콩밥|粳米 240,黑豆 120,洋蔥 25,大蒜 10,食鹽 6,豬肉 30
Argentina|牛肉餡餅|Beef empanada|エンパナーダ|엠파나다|小麥 140,牛肉 120,洋蔥 40,雞蛋 30,葡萄乾 16,食鹽 6,辣椒 8,橄欖 12
Argentina|烤腸麵包|Sausage sandwich|チョリパン|초리판|豬肉 200,小麥 140,洋蔥 30,辣椒 16,食鹽 8,番茄 20
Peru|烤雞|Rotisserie chicken|ロティサリーチキン|로티세리치킨|雞肉 280,馬鈴薯 60,檸檬 25,大蒜 12,食鹽 8,辣椒 10,粳米 30
Peru|炒牛肉|Stir-fried beef|ロモサルタード|로모살타도|牛肉 180,馬鈴薯 80,番茄 40,洋蔥 30,辣椒 12,食鹽 6,香菜 10,醬油 10,粳米 40
Chile|玉米牛肉派|Corn and beef pie|パステルデチョクロ|옥수수파이|玉米 180,牛肉 100,洋蔥 30,雞蛋 40,橄欖 16,食鹽 6,葡萄乾 12,雞肉 16
Colombia|農家拼盤|Country platter|バンデハパイサ|반데하|紅豆 80,粳米 120,牛肉 70,豬肉 40,雞蛋 40,酪梨 30,洋蔥 16,食鹽 6,番茄 16
Cuba|黑豆米飯|Rice and black beans|モロス|모로스|粳米 240,黑豆 100,洋蔥 25,大蒜 12,甜椒 20,食鹽 6,月桂葉 6
Jamaica|辣烤雞|Jerk chicken|ジャークチキン|저크치킨|雞肉 280,辣椒 20,百里香 12,洋蔥 25,大蒜 12,生薑 10,食鹽 8,檸檬 16,粳米 30
Egypt|埃及雜炊|Koshari|コシャリ|코샤리|粳米 140,小麥 80,扁豆 60,洋蔥 30,番茄 40,食鹽 6,辣椒 8,香菜 8
Morocco|古斯米蔬菜|Vegetable couscous|野菜クスクス|채소쿠스쿠스|小麥 180,胡蘿蔔 50,南瓜 50,洋蔥 25,番茄 30,羊肉 40,食鹽 6,辣椒 8,香菜 8
Lebanon|塔布勒沙拉|Tabbouleh|タッブーレ|타불레|小麥 80,番茄 100,香菜 80,洋蔥 30,檸檬 30,食鹽 6,薄荷 16,黃瓜 30
Lebanon|豌豆泥|Chickpea-style dip|フムス|후무스|豌豆 240,檸檬 40,大蒜 16,食鹽 8,花生油 20,辣椒 8
Lebanon|烤肉捲|Shawarma|シャワルマ|샤와르마|羊肉 200,小麥 80,洋蔥 25,番茄 30,優格 30,食鹽 6,辣椒 8,香菜 8
Israel|北非蛋|Shakshuka|シャクシュカ|샤크슈카|雞蛋 140,番茄 180,洋蔥 30,甜椒 30,大蒜 12,食鹽 8,辣椒 10,香菜 10
Iran|波斯燉菜|Herb stew|ゴルメサブジ|고르메사브지|羊肉 120,菠菜 80,扁豆 50,洋蔥 25,生薑 8,食鹽 6,檸檬 16,粳米 80,香菜 16
Iran|石榴核桃燉雞|Pomegranate walnut chicken|フェセンジャーン|페센잔|雞肉 180,核桃 60,石榴 40,洋蔥 25,食鹽 6,粳米 80,肉桂 6
Russia|俄羅斯餃子|Pelmeni|ペリメニ|펠메니|小麥 180,牛肉 120,洋蔥 40,食鹽 8,胡椒 6,優格 30,雞蛋 16
Russia|俄式炒牛肉|Beef stroganoff|ストロガノフ|스트로가노프|牛肉 200,洋蔥 30,洋菇 40,牛奶 50,奶油 16,食鹽 6,小麥 12,胡椒 6
Russia|薄餅|Blini|ブリヌイ|블리니|小麥 140,雞蛋 50,牛奶 140,奶油 30,白糖 20,食鹽 4,優格 30
Poland|波蘭餃子|Pierogi|ピエロギ|피에로기|小麥 160,馬鈴薯 120,起司 50,洋蔥 30,奶油 16,食鹽 6,雞蛋 16
Ukraine|烏克蘭餃子|Varenyky|ヴァレニキ|바레니키|小麥 160,馬鈴薯 100,起司 40,洋蔥 25,奶油 16,食鹽 6,雞蛋 16
Hungary|紅椒雞|Chicken paprikash|パプリカチキン|파프리카슈|雞肉 200,洋蔥 40,辣椒 20,番茄 40,優格 40,食鹽 8,小麥 10
Sweden|醃鯡魚配馬鈴薯|Pickled herring plate|ニシンと芋|청어와감자|沙丁魚 160,馬鈴薯 140,洋蔥 30,醋 16,食鹽 6,奶油 12,香菜 8
Norway|烤鮭魚|Baked salmon|焼きサーモン|연어구이|鮭魚 300,馬鈴薯 80,檸檬 20,食鹽 8,奶油 12,香菜 8
Finland|鮭魚湯|Salmon soup|ロヒケイット|연어수프|鮭魚 180,馬鈴薯 100,洋蔥 25,牛奶 60,奶油 12,食鹽 6,香菜 8
Netherlands|豌豆湯|Pea soup|エンドウ豆スープ|완두콩수프|豌豆 200,豬肉 60,洋蔥 30,胡蘿蔔 25,芹菜 20,食鹽 8,馬鈴薯 30
Belgium|比利時燉牛肉|Beef carbonade|カルボナード|카르보나드|牛肉 220,洋蔥 50,小麥 40,食鹽 8,百里香 8,芥末 8,馬鈴薯 40
Belgium|華夫餅|Waffle|ワッフル|와플|小麥 160,雞蛋 60,牛奶 140,奶油 30,白糖 30,食鹽 4,蜂蜜 16
Switzerland|馬鈴薯餅|Rosti|ロスティ|뢰슈티|馬鈴薯 360,洋蔥 30,奶油 20,食鹽 8,火腿 30
Switzerland|穀片優格|Muesli|ミューズリー|뮤즐리|燕麥 180,優格 120,蘋果 60,蜂蜜 20,核桃 20,牛奶 40
Austria|蘋果卷|Apple strudel|シュトルーデル|사과슈트루델|蘋果 220,小麥 100,奶油 30,白糖 30,核桃 20,食鹽 4,肉桂 8,葡萄乾 16
Portugal|青菜湯|Green soup|カルドヴェルデ|칼도베르데|馬鈴薯 180,高麗菜 140,洋蔥 30,大蒜 12,食鹽 8,花生油 12,豬肉 30
Portugal|烤沙丁魚|Grilled sardines|イワシのグリル|정어기구이|沙丁魚 280,馬鈴薯 60,洋蔥 25,檸檬 25,食鹽 8,香菜 10,花生油 10
Canada|肉派|Meat pie|ミートパイ|미트파이|小麥 140,豬肉 100,牛肉 50,洋蔥 30,馬鈴薯 40,食鹽 8,百里香 6,奶油 10
Australia|肉派|Meat pie|ミートパイ|미트파이|小麥 140,牛肉 140,洋蔥 30,馬鈴薯 40,食鹽 8,百里香 6,番茄 16
New Zealand|蛋白霜餅|Pavlova|パブロバ|파블로바|蛋白 160,白糖 80,草莓 80,奇異果 50,奶油 30,檸檬 10
Ethiopia|扁豆辣醬|Spiced lentils|ミスルウォト|미스르워트|扁豆 240,洋蔥 40,辣椒 16,大蒜 12,生薑 8,食鹽 8,番茄 30,香菜 10
Nigeria|花生菠菜湯|Peanut greens soup|エグシスープ|땅콩시금치수프|花生 80,菠菜 120,牛肉 60,洋蔥 25,辣椒 12,食鹽 8,番茄 25,粳米 40
Ghana|紅豆米飯|Rice and beans|ワーチェ|와체|粳米 220,紅豆 100,洋蔥 25,辣椒 10,食鹽 6,番茄 20
Kenya|烤肉|Grilled meat|ニャマチョマ|냐마초마|牛肉 300,食鹽 10,洋蔥 30,辣椒 12,番茄 20,玉米 30
South Africa|番茄豆|Chakalaka|チャカラカ|차칼라카|菜豆 120,番茄 80,洋蔥 30,甜椒 30,辣椒 16,胡蘿蔔 30,食鹽 8,香菜 10
Senegal|洋蔥檸檬雞|Chicken yassa|プーレヤッサ|치킨야사|雞肉 220,洋蔥 100,檸檬 40,芥末 10,食鹽 8,辣椒 8,粳米 40
Pakistan|慢燉牛肉|Slow beef stew|ニハリ|니하리|牛肉 240,洋蔥 40,生薑 12,大蒜 12,辣椒 12,薑黃 8,食鹽 8,小麥 16
Nepal|扁豆配飯|Lentils and rice|ダルバート|달바트|粳米 220,扁豆 120,洋蔥 25,薑黃 8,辣椒 8,食鹽 6,番茄 20,香菜 8
Sri Lanka|炒麵餅|Chopped flatbread stir-fry|コットゥ|코뚜|小麥 180,雞肉 60,洋蔥 30,胡蘿蔔 25,雞蛋 30,辣椒 12,食鹽 6,薑黃 6
Bangladesh|芥末魚|Mustard fish|ショルシェイル|머스타드생선|鱸魚 260,芥末 20,洋蔥 25,辣椒 12,食鹽 8,薑黃 6,檸檬 16,粳米 30
Cambodia|胡椒牛肉|Pepper beef|ロクラック|록락|牛肉 220,胡椒 12,洋蔥 25,番茄 30,生菜 30,食鹽 8,檸檬 16,醬油 10
Myanmar|茶葉沙拉|Tea leaf salad|ラペト|라펫|茶 30,生菜 120,花生 40,番茄 40,大蒜 10,檸檬 16,食鹽 6,辣椒 8,蝦米 10
Laos|糯米烤雞|Sticky rice and grilled chicken|もち米と鶏|찹쌀구이치킨|糯米 220,雞肉 180,辣椒 12,大蒜 10,食鹽 8,檸檬 16,薄荷 10
Saudi Arabia|牛奶雞飯|Milk rice with chicken|サリーグ|살릭|粳米 200,牛奶 120,雞肉 100,食鹽 6,肉桂 6,洋蔥 16
United Arab Emirates|香料羊肉飯|Spiced lamb rice|マチブース|마크부스|粳米 200,羊肉 120,洋蔥 25,番茄 20,葡萄乾 16,肉桂 6,食鹽 6,檸檬 12
Jordan|洋蔥烤雞|Onion flatbread chicken|ムサハン|무사한|雞肉 200,洋蔥 80,小麥 80,松子 16,食鹽 6,檸檬 12,辣椒 8
Egypt|蠶豆餅|Fava patties|ターメイヤ|타메야|蠶豆 240,洋蔥 30,香菜 30,大蒜 12,食鹽 8,辣椒 8,小麥 20
Morocco|扁豆湯|Lentil soup|ハリラ|하리라|扁豆 140,番茄 60,洋蔥 25,羊肉 40,香菜 16,食鹽 6,薑黃 6,檸檬 12,芹菜 12
Russia|紅菜冷湯|Cold beet soup|ホロドニック|홀로드닉|甜菜 160,黃瓜 60,雞蛋 50,優格 80,洋蔥 20,食鹽 6,香菜 10,馬鈴薯 30
Poland|豬排|Breaded pork cutlet|カツレツ|돈가스|豬肉 220,小麥 40,雞蛋 40,馬鈴薯 60,高麗菜 40,食鹽 8,奶油 10
Hungary|燉牛肉土豆|Beef and potato|グヤーシュポテト|굴라시감자|牛肉 180,馬鈴薯 100,洋蔥 40,辣椒 16,番茄 30,食鹽 8,胡蘿蔔 20
Greece|烤魚|Grilled fish|焼き魚|구운생선|鯛魚 280,檸檬 30,洋蔥 25,番茄 30,食鹽 8,香菜 12,花生油 12
Italy|烤魚|Roasted fish|焼き魚|오븐생선|鯛魚 260,馬鈴薯 60,番茄 30,大蒜 12,食鹽 8,香菜 10,檸檬 16
Spain|烘蛋|Baked eggs|ウエボス|우에보스|雞蛋 140,番茄 120,馬鈴薯 60,洋蔥 25,甜椒 25,食鹽 6,辣椒 8
France|烤雞|Roast chicken|ローストチキン|로스트치킨|雞肉 280,馬鈴薯 60,洋蔥 25,百里香 10,食鹽 8,胡蘿蔔 20,大蒜 10
Japan|茶泡飯|Rice with tea|お茶漬け|오차즈케|粳米 300,綠茶 20,鮭魚 80,海帶 20,食鹽 6,蔥 12
South Korea|冷麵|Cold noodles|冷麺|냉면|蕎麥 200,牛肉 60,黃瓜 40,梨 30,雞蛋 40,醋 16,食鹽 8,芥末 8
China|炸醬麵|Noodles with soybean sauce|ジャージャー麺|짜장면|小麥 220,豬肉 80,黃豆 30,黃瓜 40,蔥 16,醬油 20,食鹽 6,生薑 8
China|小米粥|Millet porridge|粟粥|좁쌀죽|小米 300,紅棗 30,南瓜 40,食鹽 6,花生 16
Taiwan|虱目魚粥|Milkfish congee|サバヒー粥|밀크피시죽|虱目魚 160,粳米 200,生薑 12,蔥 12,食鹽 8,香菜 8
Taiwan|蘿蔔糕|Radish cake|大根餅|무떡|白蘿蔔 180,粳米 160,蝦米 20,香菇 25,食鹽 8,蔥 12
Japan|茶碗蒸|Steamed egg custard|茶碗蒸し|차완무시|雞蛋 140,牛奶 40,蝦 40,香菇 25,雞肉 40,食鹽 6,蔥 8
South Korea|年糕湯|Rice cake soup|トックク|떡국|粳米 240,牛肉 60,雞蛋 40,蔥 20,食鹽 8,醬油 12,大蒜 8
Thailand|黃咖哩雞|Yellow curry chicken|イエローカレー|옐로커리|雞肉 160,椰子汁 140,馬鈴薯 50,洋蔥 25,薑黃 10,辣椒 10,食鹽 6,香茅 8
India|椰汁魚咖哩|Coconut fish curry|魚カレー|생선커리|石斑魚 200,椰子汁 140,洋蔥 25,薑黃 8,辣椒 10,食鹽 6,檸檬 16,番茄 20
Indonesia|黃薑牛肉|Beef in coconut|ビーフレンダン風|코코넛소고기|牛肉 200,椰子汁 120,香茅 12,辣椒 12,洋蔥 20,食鹽 6,薑黃 6
Vietnam|雞絲河粉|Chicken noodle soup|鶏肉フォー|닭고기쌀국수|雞肉 140,粳米 180,洋蔥 20,生薑 10,香菜 16,檸檬 16,食鹽 6,辣椒 6,黃豆芽 20
Mexico|玉米豬肉湯|Pork and hominy soup|ポソレ|포솔레|豬肉 180,玉米 140,洋蔥 25,辣椒 16,食鹽 8,香菜 12,檸檬 16,高麗菜 20
United States|秋葵湯|Gumbo|ガンボ|검보|秋葵 80,蝦 60,雞肉 50,洋蔥 25,芹菜 20,甜椒 25,番茄 30,粳米 40,食鹽 8
United Kingdom|魚派|Fish pie|フィッシュパイ|피시파이|鱈魚 160,馬鈴薯 120,牛奶 50,奶油 16,洋蔥 20,食鹽 6,雞蛋 16,香菜 8
Germany|馬鈴薯沙拉|Potato salad|ポテトサラダ|감자샐러드|馬鈴薯 280,洋蔥 30,醋 20,食鹽 8,芥末 8,火腿 30,香菜 8
Spain|番茄麵包|Tomato bread|パン・コン・トマテ|토마토빵|小麥 200,番茄 160,大蒜 16,食鹽 8,花生油 16
Italy|蔬菜烤盤|Roasted vegetables|焼き野菜|구운채소|茄子 100,番茄 80,甜椒 60,洋蔥 40,馬鈴薯 50,食鹽 8,羅勒 10,大蒜 8
France|馬鈴薯焗烤|Potato gratin|グラタン|그라탕|馬鈴薯 280,牛奶 80,奶油 25,起司 30,大蒜 8,食鹽 6,百里香 6
Japan|日式煎餃|Pan-fried dumplings|餃子|교자|小麥 160,豬肉 140,高麗菜 70,蔥 20,生薑 10,醬油 12,食鹽 6,麻油 8
China|雲吞|Wontons|ワンタン|완탕|小麥 160,豬肉 100,蝦 60,蔥 16,生薑 10,醬油 12,食鹽 6,麻油 8
Taiwan|肉羹|Thick pork soup|肉羹|육갱|豬肉 180,小麥 40,香菇 30,竹筍 30,食鹽 8,胡椒 6,香菜 10,蔥 10
Hong Kong|及第粥|Offal congee|及第粥|급제죽|粳米 180,豬肉 50,豬肝 40,豬腸 40,生薑 10,蔥 12,食鹽 8
Japan|炸蝦丼|Shrimp tempura bowl|天丼|텐동|蝦 140,粳米 200,小麥 30,雞蛋 20,醬油 12,食鹽 6,蔥 8
South Korea|醬湯|Soybean paste stew|テンジャンチゲ|된장찌개|黃豆 60,豆腐 120,馬鈴薯 50,洋蔥 25,辣椒 12,食鹽 6,蔥 10,豬肉 20
Thailand|泰式羅勒雞|Basil chicken|ガパオガイ|바질치킨|雞肉 200,羅勒 30,辣椒 20,大蒜 12,洋蔥 20,醬油 12,食鹽 6,雞蛋 30,粳米 60
India|優格雞肉|Yogurt chicken|チキンティッカ|치킨티카|雞肉 240,優格 100,生薑 10,大蒜 10,薑黃 8,辣椒 10,食鹽 6,檸檬 16
""".strip()


def load_foods():
    sheet = xlrd.open_workbook(FOODS_PATH).sheet_by_index(0)
    by_name = {}
    for row in range(1, sheet.nrows):
        names = [str(sheet.cell_value(row, col)).strip() for col in range(4)]
        record = {
            "benefit": str(sheet.cell_value(row, 4)).strip(),
            "ban": str(sheet.cell_value(row, 5)).strip(),
            "nutrient": str(sheet.cell_value(row, 6)).strip(),
        }
        for name in names:
            if name:
                by_name[name] = record
    return by_name


def scale_to(pairs, target=TARGET):
    total = sum(weight for _, weight in pairs)
    if total <= 0:
        raise ValueError("empty recipe")
    exact = [weight * target / total for _, weight in pairs]
    grams = [int(value) for value in exact]
    leftover = target - sum(grams)
    order = sorted(range(len(exact)), key=lambda i: (exact[i] - grams[i], exact[i]), reverse=True)
    for index in range(max(leftover, 0)):
        grams[order[index % len(order)]] += 1
    for index, gram in enumerate(grams):
        if gram < 1:
            grams[index] = 1
    while sum(grams) > target:
        index = max(range(len(grams)), key=lambda i: grams[i])
        if grams[index] <= 1:
            break
        grams[index] -= 1
    while sum(grams) < target:
        index = max(range(len(grams)), key=lambda i: pairs[i][1])
        grams[index] += 1
    return [(name, gram) for (name, _), gram in zip(pairs, grams)]


def parse_existing(sheet):
    rows = []
    for row in range(1, sheet.nrows):
        text = str(sheet.cell_value(row, 5))
        pairs = []
        for part in text.split("、"):
            part = part.strip()
            if not part:
                continue
            match = re.match(r"^(.+?) (\d+)克$", part)
            if not match:
                raise SystemExit(f"bad existing recipe: {part}")
            pairs.append((match.group(1), int(match.group(2))))
        rows.append(
            (
                str(sheet.cell_value(row, 0)).strip(),
                str(sheet.cell_value(row, 1)).strip(),
                str(sheet.cell_value(row, 2)).strip(),
                str(sheet.cell_value(row, 3)).strip(),
                str(sheet.cell_value(row, 4)).strip(),
                pairs,
            )
        )
    return rows


def parse_new():
    rows = []
    for raw in NEW.splitlines():
        line = raw.strip()
        if not line or "|SKIP" in line:
            continue
        country, zh, en, ja, ko, items = line.split("|")
        pairs = []
        for token in items.split(","):
            name, weight = token.rsplit(" ", 1)
            pairs.append((name.strip(), int(weight)))
        rows.append((country.strip(), zh.strip(), en.strip(), ja.strip(), ko.strip(), pairs))
    return rows


def join_lookup(scaled, foods, field):
    chunks = []
    for name, _gram in scaled:
        text = foods[name][field]
        if text:
            chunks.append(f"{name}:{text}")
    return ";".join(chunks)


def main():
    foods = load_foods()
    existing = parse_existing(xlrd.open_workbook(RECIPE_PATH).sheet_by_index(0))
    added = parse_new()
    seen = {(country, zh) for country, zh, *_ in existing}
    seen_en = {(country, en.lower()) for country, _zh, en, *_ in existing}
    merged = list(existing)
    for row in added:
        country, zh, en, _ja, _ko, _pairs = row
        if (country, zh) in seen or (country, en.lower()) in seen_en:
            continue
        seen.add((country, zh))
        seen_en.add((country, en.lower()))
        merged.append(row)

    missing = []
    for country, _zh, _en, _ja, _ko, pairs in merged:
        for name, _weight in pairs:
            if name not in foods:
                missing.append((country, name))
    if missing:
        raise SystemExit("unmatched: " + str(missing[:30]))

    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet("食譜")
    header_style = xlwt.easyxf(
        "font: name 微軟正黑體, bold on, height 240, colour white;"
        "align: horiz center, vert center, wrap on;"
        "pattern: pattern solid, fore_colour gray80;"
        "borders: left thin, right thin, top thin, bottom thin"
    )
    cell_style = xlwt.easyxf(
        "font: name 微軟正黑體, height 200;"
        "align: vert top, wrap on;"
        "borders: left thin, right thin, top thin, bottom thin"
    )
    headers = ["國家", "中文食譜", "英文食譜", "日文食譜", "韓文食譜", "食譜", "益處", "禁忌", "元素", "過敏原"]
    widths = [28, 22, 36, 28, 24, 78, 55, 55, 80, 28]
    for col, (header, width) in enumerate(zip(headers, widths)):
        sheet.write(0, col, header, header_style)
        sheet.col(col).width = 256 * width
    sheet.row(0).height_mismatch = True
    sheet.row(0).height = 360
    sheet.panes_frozen = True
    sheet.horz_split_pos = 1

    merged.sort(key=lambda item: (item[0].lower(), item[1]))
    for row_index, (country, zh, en, ja, ko, pairs) in enumerate(merged, start=1):
        scaled = scale_to(pairs)
        if sum(gram for _, gram in scaled) != TARGET:
            raise SystemExit(f"weight {country} {zh}")
        recipe = "、".join(f"{name} {gram}克" for name, gram in scaled)
        values = [
            country,
            zh,
            en,
            ja,
            ko,
            recipe,
            join_lookup(scaled, foods, "benefit"),
            join_lookup(scaled, foods, "ban"),
            join_lookup(scaled, foods, "nutrient"),
            "、".join(name for name, _gram in scaled if name in ALLERGENS),
        ]
        for col, value in enumerate(values):
            if len(value) > 32000:
                raise SystemExit(f"too long {country} {zh} col {col}")
            sheet.write(row_index, col, value, cell_style)
        sheet.row(row_index).height_mismatch = True
        sheet.row(row_index).height = 1100
    book.save(RECIPE_PATH)
    print("rows", len(merged), "added", len(merged) - len(existing))


if __name__ == "__main__":
    main()
