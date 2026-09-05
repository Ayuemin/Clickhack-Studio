from pathlib import Path
import sys, json

root=Path(sys.argv[1])
dict_path=Path(sys.argv[2])

# Version
bg=root/'app/build.gradle'
b=bg.read_text(encoding='utf-8')
b=b.replace('versionCode 13','versionCode 14').replace("versionName '1.3.0'","versionName '1.3.1'")
bg.write_text(b,encoding='utf-8')

# Compact Abramov dictionary into an APK asset
src=json.loads(dict_path.read_text(encoding='utf-8'))
compact={}
for it in src.get('wordlist',[]):
    if not isinstance(it,dict): continue
    name=str(it.get('name') or '').strip().lower()
    syn=it.get('synonyms')
    if not name or not isinstance(syn,list): continue
    vals=[]
    for x in syn:
        v=str(x).strip()
        if v and v.casefold() not in {q.casefold() for q in vals}: vals.append(v)
    if vals: compact[name]=vals
asset=root/'app/src/main/assets/synonyms_compact.json'
asset.write_text(json.dumps(compact,ensure_ascii=False,separators=(',',':')),encoding='utf-8')

# Native Java: bundled dictionary + streaming import for large wordlist JSON
java=root/'app/src/main/java/ru/dzenprep/texteditor/MainActivity.java'
s=java.read_text(encoding='utf-8')
s=s.replace('import android.webkit.WebViewClient;\n', 'import android.webkit.WebViewClient;\nimport android.util.JsonReader;\n')
s=s.replace('import java.io.ByteArrayOutputStream;\n', 'import java.io.ByteArrayOutputStream;\nimport java.io.ByteArrayInputStream;\nimport java.io.InputStreamReader;\n')
s=s.replace('    private final Map<String, List<String>> synonymMap = new HashMap<>();\n',
'''    private final Map<String, List<String>> synonymMap = new HashMap<>(); // внешний пользовательский словарь\n    private final Map<String, List<String>> bundledSynonymMap = new HashMap<>(); // встроенный компактный словарь\n''')
s=s.replace('        web.addJavascriptInterface(new DictionaryBridge(), "AndroidDictionary");\n        loadSavedDictionary();\n',
'''        web.addJavascriptInterface(new DictionaryBridge(), "AndroidDictionary");\n        loadBundledDictionary();\n        loadSavedDictionary();\n''')
s=s.replace('                List<String> values = synonymMap.get(key);\n                JSONObject out = new JSONObject();\n',
'''                List<String> values = synonymMap.get(key);\n                if (values == null || values.isEmpty()) values = bundledSynonymMap.get(key);\n                JSONObject out = new JSONObject();\n''')
s=s.replace('''                out.put("name", synonymName);\n                out.put("count", synonymCount);\n                return out.toString();\n''',
'''                out.put("name", synonymName);\n                out.put("count", synonymCount);\n                out.put("builtinCount", bundledSynonymMap.size());\n                return out.toString();\n''')
s=s.replace('''                String text = decodeText(bytes);\n                Map<String, List<String>> parsed = parseDictionary(text);\n''',
'''                Map<String, List<String>> parsed = parseDictionaryBytes(bytes);\n''',1)
s=s.replace('''            Map<String, List<String>> parsed = parseDictionary(decodeText(bytes));\n''',
'''            Map<String, List<String>> parsed = parseDictionaryBytes(bytes);\n''')
marker='    private Map<String, List<String>> parseDictionary(String text) throws Exception {\n'
insert=r'''    private void loadBundledDictionary() {
        try (InputStream in = getAssets().open("synonyms_compact.json");
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) != -1) out.write(buf, 0, n);
            Map<String, List<String>> parsed = parseDictionary(decodeText(out.toByteArray()));
            synchronized (bundledSynonymMap) {
                bundledSynonymMap.clear();
                bundledSynonymMap.putAll(parsed);
            }
        } catch (Exception ignored) { }
    }

    private Map<String, List<String>> parseDictionaryBytes(byte[] bytes) throws Exception {
        if (bytes == null || bytes.length == 0) return new HashMap<>();
        int probeLen = Math.min(bytes.length, 8192);
        String probe = new String(bytes, 0, probeLen, StandardCharsets.UTF_8);
        if (probe.contains("\"wordlist\"")) return parseAbramovStreaming(bytes);
        return parseDictionary(decodeText(bytes));
    }

    private Map<String, List<String>> parseAbramovStreaming(byte[] bytes) throws Exception {
        Map<String, List<String>> out = new HashMap<>();
        JsonReader reader = new JsonReader(new InputStreamReader(new ByteArrayInputStream(bytes), StandardCharsets.UTF_8));
        try {
            reader.beginObject();
            while (reader.hasNext()) {
                String field = reader.nextName();
                if (!"wordlist".equals(field)) { reader.skipValue(); continue; }
                reader.beginArray();
                while (reader.hasNext()) {
                    String name = "";
                    List<String> vals = new ArrayList<>();
                    reader.beginObject();
                    while (reader.hasNext()) {
                        String itemField = reader.nextName();
                        if ("name".equals(itemField)) {
                            name = reader.nextString();
                        } else if ("synonyms".equals(itemField)) {
                            reader.beginArray();
                            while (reader.hasNext()) addSyn(vals, reader.nextString());
                            reader.endArray();
                        } else {
                            reader.skipValue();
                        }
                    }
                    reader.endObject();
                    putSynonyms(out, name, vals);
                }
                reader.endArray();
            }
            reader.endObject();
        } finally {
            try { reader.close(); } catch (Exception ignored) { }
        }
        return out;
    }

'''
if marker not in s: raise SystemExit('parse marker missing')
s=s.replace(marker,insert+marker)
java.write_text(s,encoding='utf-8')

# UI wording/status
html=root/'app/src/main/assets/www/index.html'
h=html.read_text(encoding='utf-8')
h=h.replace('<title>Дзен Текст 1.2</title>','<title>Дзен Текст 1.3.1</title>')
h=h.replace('''<div class="smallNote">Встроенный словарь работает без интернета. Можно подключить внешний JSON/TXT-словарь. Поддерживается обычная карта «слово → синонимы» и JSON словаря Н. Абрамова с полем <b>wordlist</b>.</div>\n    <div id="dictStatus" class="dictStatus">Внешний словарь: не загружен</div>\n    <div class="settingActions"><button class="nativeBtn" type="button" onclick="chooseSynonymDictionary()">Импортировать</button><button class="nativeBtn" type="button" onclick="clearSynonymDictionary()">Удалить внешний</button></div>''',
'''<div class="smallNote">Большой русский словарь уже встроен в приложение и работает без интернета. При желании можно подключить свой JSON/TXT-словарь поверх встроенного. Поддерживается обычная карта «слово → синонимы» и JSON словаря Н. Абрамова с полем <b>wordlist</b>.</div>\n    <div id="dictStatus" class="dictStatus">Встроенный словарь загружается…</div>\n    <div class="settingActions"><button class="nativeBtn" type="button" onclick="chooseSynonymDictionary()">Импортировать свой</button><button class="nativeBtn" type="button" onclick="clearSynonymDictionary()">Удалить внешний</button></div>''')
old="function updateDictStatus(){const el=document.getElementById('dictStatus');let txt='Внешний словарь: не загружен';try{if(window.AndroidDictionary&&typeof AndroidDictionary.status==='function'){const o=JSON.parse(AndroidDictionary.status()||'{}');if(o.count)txt=`Внешний словарь: <b>${escapeHtml(o.name||'словарь')}</b> · ${o.count} слов`}}catch(e){}if(window.browserSynonymCount)txt=`Внешний словарь: <b>${escapeHtml(window.browserSynonymName||'словарь')}</b> · ${window.browserSynonymCount} слов (сеанс)`;el.innerHTML=txt}"
new="function updateDictStatus(){const el=document.getElementById('dictStatus');let txt='Встроенный словарь: загружается…';try{if(window.AndroidDictionary&&typeof AndroidDictionary.status==='function'){const o=JSON.parse(AndroidDictionary.status()||'{}');const built=Number(o.builtinCount||0);txt=built?`Встроенный словарь: <b>${built}</b> слов`:'Встроенный словарь: не загружен';if(o.count)txt+=`<br>Внешний: <b>${escapeHtml(o.name||'словарь')}</b> · ${o.count} слов`;else txt+='<br>Внешний словарь: не загружен'}}catch(e){}if(window.browserSynonymCount)txt=`Внешний словарь: <b>${escapeHtml(window.browserSynonymName||'словарь')}</b> · ${window.browserSynonymCount} слов (сеанс)`;el.innerHTML=txt}"
if old not in h: raise SystemExit('status function missing')
h=h.replace(old,new)
html.write_text(h,encoding='utf-8')

print('v1.3.1 patch applied; bundled entries:',len(compact))
