<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.md">English</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop/brand/main/logos/sprite-foundry/readme.png" alt="Sprite Foundry" width="600">
</p>

<p align="center">
  <strong>Headless, canon-bound sprite pipeline — 8-direction pixel-art packs for 2.5D RPGs</strong>
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/sprite-foundry/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/sprite-foundry/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="https://mcp-tool-shop-org.github.io/sprite-foundry/"><img src="https://img.shields.io/badge/docs-handbook-blue" alt="Handbook"></a>
</p>

---

स्प्राइट फाउंड्री एक स्थानीय-आधारित एसेट पाइपलाइन है जो सामान्य और गहराई मानचित्रों के साथ 8-दिशात्मक पिक्सेल स्प्राइट्स उत्पन्न, समीक्षा और निर्यात करती है। यह कंट्रोलनेट मॉर्फोलॉजी नियंत्रण (8 बॉडी क्लास), जीवनचक्र ट्रैकिंग के लिए SQLite, और फिनिश-लैब लाइटिंग सत्यापन के लिए Godot 4.6 के साथ पीढ़ी के लिए ComfyUI को संचालित करता है - ये सभी एक ही CLI से नियंत्रित होते हैं।

> **यह फैक्ट्री जिन स्प्राइट पैक्स का उत्पादन करती है, उन्हें npm पर `@sprite-foundry` दायरे में प्रकाशित किया जाता है**, जो [sprite-foundry-packs](https://github.com/mcp-tool-shop-org/sprite-foundry-packs) मोनोरेपो से प्राप्त होते हैं। यह रेपो फैक्ट्री है; वह रेपो स्टोरफ्रंट है।

## आर्किटेक्चर

```
Subject Sheet ──► ComfyUI Generation ──► Mechanical Gates
                  (SDXL + LoRA +          (transparency,
                   ControlNet)             dimensions, count)
                                                │
                                                ▼
                                        Raw/Pixel Review
                                                │
                                                ▼
                                    Normal + Depth Map Gen
                                                │
                                                ▼
                                     Godot Finish Lab
                                     (4 lighting states)
                                                │
                                                ▼
                                      Deterministic Export
                                      (manifest + checksums)
```

## सूची

12 लेन में 92 उत्पादन निर्यात पैक:

| लेन | संख्या | विषय |
|------|-------|----------|
| राक्षस | 16 | बेल वार्डन, बोन वीवर, क्लॉक गोलेम, ग्रिनिंग आइडल, हाइव कीपर, हॉलो नाइट, इंक शेड, लैंटर्न एंग्लर, मिरर स्टॉकर, मड रेवेनेंट, रैट किंग, रूट पपेट, स्पोर मदर, टीथ कलेक्टर, थ्रोट सिंगर, वाइवरन |
| कस्बे के लोग | 16 | बारमेड, भिखारी, लोहार, बच्चा, बुजुर्ग, किसान, मछुआरा, गार्ड, हर्बलिस्ट, सराय चलाने वाला, लैम्पलाइटर, व्यापारी, संगीतकार, कुलीन, लेखक, अस्तबल का सहायक |
| गोब्लिन | 8 | आर्चर, बॉम्बर, ब्रूट, ग्रंट, स्काउट, शमां, वारचीफ, वुल्फ राइडर |
| नायक | 8 | बर्बरियन, क्लैरिक, फाइटर, मेज, भिक्षु, पलाडिन, रेंजर, रोग |
| समुद्री डाकू | 8 | कप्तान, कटथ्रोट, डूबे हुए, गवर्नर, नौसेना का नाविक, पिस्टोलेर, क्वार्टरमास्टर, समुद्री पुजारी |
| खलनायक | 8 | हत्यारा, ब्लैकगार्ड, पंथ का पुजारी, डार्क भिक्षु, भयानक रेंजर, नेक्रोमेंसर, रीवर, वारलॉर्ड |
| ज़ोंबी | 8 | ब्लोटर, एलिट, हजमत, दंगा करने वाला, धावक, शंबलर, कंकाल, कार्यकर्ता |
| जीव | 6 | कार्गो बीस्ट, ड्रिफ्ट मॉव, स्किटर ड्रोन, ड्रिफ्ट लर्कर, वॉयड रैप्टर, केथ हीलर-ड्रोन |
| दल | 7 | सेरा वेले, इलेन मार, थल, थल (हैज़र्ड सूट), वारेक, केल मोरो, हल डाइवर |
| शत्रुतापूर्ण | 3 | स्केव रेडर, रीच पाइरेट, कॉम्पैक्ट इंटरडिक्शन एजेंट |
| अधिकार | 2 | कॉम्पैक्ट पेट्रोल ऑफिसर, वेशान हाउस एनवॉय |
| नागरिक | 2 | नेरा क्विल, ऑरिन ब्रोकर |

## मॉन्स्टर लेन

गैर-मानवीय जीव मानक मानवीय कंकाल के बजाय बॉडी-क्लास-विशिष्ट कंट्रोलनेट गहराई गाइड का उपयोग करते हैं। प्रत्येक बॉडी क्लास में अपनी स्वयं की गहराई संदर्भ सिल्हूट, कंट्रोलनेट शक्ति और समय पैरामीटर होते हैं।

| बॉडी क्लास | गहराई शक्ति | अंत % | जीव |
|------------|---------------|-------|-----------|
| अमोर्फस | 0.35 | 65% | रैट किंग, स्पोर मदर, मड रेवेनेंट |
| चौड़ा/चपटा | 0.40 | 70% | ग्रिनिंग आइडल |
| लंबा/पतला | 0.40 | 70% | लैंटर्न एंग्लर, रूट पपेट |

गहराई गाइड संयुक्त-मुक्त आदिम (ब्लॉब, खंभे, स्तंभ) होते हैं जो कंकाल या अंग प्लेसमेंट को निर्धारित किए बिना द्रव्यमान और अभिविन्यास को लॉक करते हैं। चरित्र कॉन्फ़िगरेशन में `body_class` फ़ील्ड स्वचालित रूप से सही प्रीसेट का चयन करता है:

```bash
# Body class auto-resolved from config
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json

# CLI override
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json --body-class tall_thin
```

## निर्यात अनुबंध v1.0.0 (स्थिर)

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, SHA-256 checksums, provenance)
```

- 8 दिशाएँ: सामने, सामने_बाएं, बाएं, पीछे_बाएं, पीछे, पीछे_दाएं, दाएं, सामने_दाएं
- 48×48 पारदर्शी PNG, केंद्र_नीचे पिवट
- उपभोक्ता लोड करने से पहले `schema_version: "1.0.0"` को मान्य करते हैं

## पूर्व आवश्यकताएँ

- पायथन 3.11+
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) स्थानीय रूप से चल रहा है (पीढ़ी के लिए)
- Godot 4.6 (फिनिश लैब रेंडरिंग के लिए)
- NVIDIA GPU की अनुशंसा की जाती है (RTX 5090 / 32 GB का परीक्षण किया गया; न्यूनतम 16 GB)

## त्वरित शुरुआत

```bash
# Clone
git clone https://github.com/mcp-tool-shop-org/sprite-foundry.git
cd sprite-foundry

# Initialize the registry
python -m foundry init

# Register a subject
python -m foundry subject-add sera_vale "Sera Vale" --role crew --consumer my-game

# Check the full pipeline status
python -m foundry status
```

## CLI कमांड

| कमांड | विवरण |
|---------|-------------|
| `init` | फाउंड्री SQLite रजिस्ट्री को प्रारंभ करें |
| `subject-add` | एक नया चरित्र विषय पंजीकृत करें |
| `register-run` | ComfyUI पीढ़ी रन रिकॉर्ड करें |
| `register-attempt` | किसी रन के भीतर एक व्यक्तिगत प्रयास रिकॉर्ड करें |
| `check` | यांत्रिक सत्यापन गेट चलाएं |
| `review-show` | किसी रन के लिए समीक्षा कतार प्रदर्शित करें |
| `review-accept` | वर्तमान समीक्षा चरण में किसी प्रयास को स्वीकार करें |
| `review-reject` | एक अस्वीकृति कोड के साथ एक प्रयास को अस्वीकार करें |
| `batch-accept` | किसी रन में सभी लंबित प्रयासों को स्वीकार करें |
| `batch-reject` | एक कोड के साथ किसी रन में सभी लंबित प्रयासों को अस्वीकार करें |
| `regen` | अस्वीकृत प्रयासों के लिए पुन: पीढ़ी की कतार बनाएं |
| `attempt-detail` | एक प्रयास के लिए पूर्ण जीवनचक्र दिखाएं |
| `finish-board` | फिनिश-लैब तुलना बोर्ड उत्पन्न करें |
| `status` | पाइपलाइन स्थिति सारांश |
| `story` | किसी विषय के लिए पूर्ण उत्पत्ति कथा |
| `lineage` | एक प्रयास के लिए पुन: पीढ़ी श्रृंखला |
| `winner` | प्रत्येक दिशा में कैनोनिकल विजेता |
| `drift` | विफलता पैटर्न विश्लेषण और पास दरें |
| `metrics` | थ्रूपुट मेट्रिक्स (प्रति-रन या फाउंड्री-व्यापी) |
| `produce` | एक-कमांड: स्वीकृत रन के लिए मानचित्र + फिनिश कैप्चर |
| `export` | स्वीकृत फिनिश रन को एक नियतात्मक एसेट पैक के रूप में निर्यात करें |

## खतरा मॉडल

स्प्राइट फाउंड्री एक **स्थानीय डेवलपर टूल** है। यह नहीं करता:

- नेटवर्क तक पहुंच (ComfyUI स्थानीय होस्ट पर चलता है)
- गुप्त, टोकन या क्रेडेंशियल्स को संभालना
- टेलीमेट्री एकत्र करना या भेजना
- अपनी स्वयं की कार्यशील निर्देशिका के बाहर लिखना

फ़ाइल संचालन `exports/`, `bakeoff/`, `boards/`, `derived/` और SQLite रजिस्ट्री तक सीमित हैं। सबप्रोसेस कॉल ComfyUI के स्थानीय API और Godot हेडलेस रेंडरिंग तक सीमित हैं।

## लाइसेंस

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
</p>
