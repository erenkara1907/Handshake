# Global Mini Projects: 1-2 günde biten, global kitleye yönelik MVP'ler

Hazırlanma tarihi: 2026-11-25. `PORTFOLIO_PROJECTS.md` (Terazi, Kasa, Köprü) ve `MINI_PROJECTS.md` (Klişe, Bekçi, Panel) içindekileri tekrar etmez. Buradaki üçü kursun en az kanıtlanmış kısımlarını kapsıyor: Hafta 5 (A2A, Google ADK, Playwright MCP ile kendini doğrulayan ajan) ve Hafta 4'ün Deep Agents kısmı.

Hedef kitle global. Repo, README, arayüz ve ilk LinkedIn gönderisi İngilizce olacak; Türkçe gönderi istersen ikinci sırada.

Bütçe sıfır. Üçünde de ortak tasarım kararı: **sunucuda LLM yok.** Her biri kullanıcının kendi makinesinde ve kendi ücretsiz anahtarıyla çalışan bir CLI, sonuçlar ise GitHub Pages'te statik olarak yayınlanıyor. Gönderi ne kadar tutarsa tutsun senin kotan yanmaz, demo çökmez. Ücretsiz servis limitleri için `PORTFOLIO_PROJECTS.md` bölüm 2'ye bak (2026-11-14'te kontrol edildi); model adlarını her projenin ilk saatinde Groq konsolundan doğrula.

| | Clickthrough | Handshake | RepoAtlas |
|---|---|---|---|
| Ne yapar | Bir web sitesini gerçek tarayıcıyla gezip QA raporu çıkaran ajan | Farklı framework'lerde yazılmış iki ajanın A2A üzerinden pazarlık etmesi ve hangi modelin daha iyi pazarlık yaptığının ölçülmesi | Herhangi bir GitHub reposundan mimari şema ve onboarding rehberi üreten Deep Agent |
| Pekiştirdiği hafta | 5 (agent loop, `qa_agent.py`), 6 (MCP istemcisi) | 5 (ADK + A2A, framework'ler arası geçiş) | 4 (Deep Agents, sub-agent, skill) |
| Dağıtım | `uvx clickthrough <url>` (PyPI) + örnek raporlar GitHub Pages'te | Repo + replay sitesi GitHub Pages'te | `uvx repoatlas <repo-url>` (PyPI) + galeri GitHub Pages'te |
| Viral mekanik | "AI ajanına 20 popüler dev-tool sitesini test ettirdim" | "İki LLM'i 100 kez araba pazarlığına soktum, kazanan şu" | Ünlü açık kaynak repoların şemaları, "kendi reponda tek komutla dene" |

Not: İsimler geçici. Başlamadan önce GitHub ve PyPI'da isim müsait mi kontrol et; doluysa sonuna `-agent` ekle veya değiştir.

---

## Ortak kurallar

- `uv` + `pyproject.toml`, `ruff`, `pytest`, GitHub Actions CI. Notebook yok.
- Geliştirmede Ollama, yayın koşularında Groq (gerekirse Gemini veya OpenRouter `:free` yedeği). Model ve sağlayıcı config'de; kodda model adı geçmez.
- `.env.example` olsun, `.env` olmasın. Anahtar CLI'a env değişkeniyle verilir, hiçbir yere yazılmaz.
- Her ajan koşusunun adım ve token bütçesi olsun; bütçe bitince ajan durur ve elindeki kısmi sonucu raporlar.
- Testlerde gerçek LLM çağrısı yok. LLM sahte yanıtla taklit edilir, yalnızca bir `smoke` testi Ollama ile lokalde koşar.
- README sırası: tek cümle, GIF, tek komutla kurulum, örnek çıktı linki, nasıl çalışıyor (tek şema), bilinen sınırlar.
- PyPI'a yayın ve Marketplace gibi dış yayınları sen yaparsın; Claude Code'a yaptırmadan önce onay ver.

---

## 1. Clickthrough: siteni gerçek tarayıcıyla test eden QA ajanı

**Tek cümle:** `uvx clickthrough https://example.com` komutu, Playwright MCP ile gerçek bir Chromium açan bir ajanı başlatır. Ajan sitenin ana akışlarını (ana sayfa, fiyatlandırma, dokümantasyon, kayıt sayfasına ulaşma) dener; kırık linkleri, konsol hatalarını, mobil görünümdeki taşmaları ve temel erişilebilirlik sorunlarını ekran görüntüleriyle birlikte bir HTML rapora yazar.

**Viral kanca:** Kurstaki QA ajanının (oyunları oynayıp test eden ajan) gerçek dünyaya çıkmış hali. Gönderi: "I let an AI agent click through 20 dev-tool landing pages. Here is what broke." İkinci gönderi: ajanın bulduğu ama Lighthouse gibi araçların kaçırdığı bir şey. Olumsuz değil yapıcı bir dil kullan: site adı vermeden kategori bazlı bulgu, ya da önceden haber verdiğin veya açık kaynak projelerin siteleri.

**Kurstan pekiştirdiği:** Hafta 5'teki `5_agent_loop/qa_agent.py` (ADK + Playwright MCP, çağrı bütçesi, MCP yoksa fallback). Hafta 6'daki MCP istemcisi. Yeni olarak öğrettiği: ajanın tool'larını izin listesiyle kısıtlamak, ajana kendi bulgusunu kanıtlatmak (her bulguya ekran görüntüsü veya konsol çıktısı bağlanmadan rapora girmez).

### Tech stack

| Katman | Seçim |
|---|---|
| Ajan | Python, Google ADK `LlmAgent` + `McpToolset` (kurstaki gibi), `LiteLlm` ile Groq. Alternatif: OpenAI Agents SDK + `MCPServerStdio` |
| Tarayıcı | `npx @playwright/mcp` (headless). Node gerekiyor; README'de belirt |
| Güvenlik kısıtları | Yalnızca verilen alan adında gezinme (kod tarafında URL kontrolü), form gönderme ve yazma tool'ları izin listesinde yok, sayfa başına ve toplam adım sınırı, sayfalar arası bekleme |
| Deterministik kontroller | LLM'den bağımsız: HTTP durum kodları, konsol hataları, `axe-core` ile erişilebilirlik taraması (sayfaya enjekte edilir). LLM bunları yorumlar ve önceliklendirir, kendisi uydurmaz |
| Çıktı | Pydantic `Finding` (sayfa, kategori, önem, kanıt dosyası, açıklama). Jinja2 ile tek dosya HTML rapor |
| Model | Groq `openai/gpt-oss-120b` (tool calling). Sayfa snapshot'ları token yer; Faz 0'da ölç, sığmazsa Gemini Flash'ın ücretsiz katmanı (uzun context) yedek |
| Dağıtım | PyPI paketi, `uvx` ile kurulumsuz çalışır. Örnek raporlar GitHub Pages'te |

### 2 günlük plan

- **Gün 1, öğleden önce:** Kurstaki `qa_agent.py`'den yola çıkarak tek sayfalık spike: Playwright MCP'yi aç, bir sayfanın snapshot'ını al, Groq ile bir tur tool çağrısı yap. Bir sayfanın kaç token tuttuğunu ölç.
- **Gün 1, öğleden sonra:** Alan adı kısıtı, tool izin listesi, adım bütçesi, deterministik kontroller (durum kodu, konsol, axe). Bunların testleri.
- **Gün 2, öğleden önce:** `Finding` şeması, kanıt zorunluluğu, HTML rapor. Kendi sitende veya bir açık kaynak projenin dokümantasyon sitesinde uçtan uca dene.
- **Gün 2, öğleden sonra:** CLI (`typer`), README, GIF, 5-10 örnek raporu Pages'e koy, PyPI.

### Riskler

- **Token tüketimi.** Erişilebilirlik ağacı snapshot'ları büyük. Sayfa sayısını (varsayılan 5) ve snapshot boyutunu sınırla.
- **Başkalarının sitesi.** Yalnızca herkese açık sayfalar, form yok, giriş yok, düşük hız. README'de "only run against sites you own or have permission to test" uyarısı. robots.txt'e uyulur.
- **Halüsinasyon.** Kanıtı olmayan bulgu rapora girmez kuralı kodda uygulanır, prompt'ta değil.

### Claude Code başlangıç promptu

```
New repo: a CLI QA agent that browses a website with Playwright MCP and writes an HTML
report. Read Project 1 (Clickthrough) in GLOBAL_PROJECTS.md, and the course reference
implementation at 5_agent_frameworks/5_agent_loop/qa_agent.py in the agents repo.
First do the Day 1 spike: verify from current Google ADK and @playwright/mcp docs how to
run ADK with LiteLlm (Groq) plus McpToolset over stdio and how to restrict the tool list.
Measure tokens for one page snapshot. Then propose the plan for domain lock, tool
allowlist, step budget and deterministic checks. Code with TDD after I approve.
```

---

## 2. Handshake: iki ajan, iki framework, A2A üzerinden pazarlık

**Tek cümle:** Google ADK ile yazılmış bir alıcı ajan ile Pydantic AI (veya CrewAI) ile yazılmış bir satıcı ajan, A2A protokolü üzerinden ikinci el bir araba (veya bir SaaS sözleşmesi) için pazarlık eder. Her birinin gizli kısıtı var (alıcının bütçesi, satıcının taban fiyatı). Hakem kodu anlaşmanın geçerliliğini deterministik olarak kontrol eder. Model eşleşmeleri onlarca kez koşulur ve "hangi model en iyi pazarlıkçı" tablosu çıkar.

**Viral kanca:** Hem eğlenceli hem ölçülmüş. Gönderi: "I made Llama and GPT-OSS negotiate a used car 100 times. One of them kept leaking its own budget." Gizli bilgiyi sızdırma, blöf ve anlaşmasız ayrılma oranları herkesin yorum yapacağı türden bulgular. Replay sitesinde tek bir pazarlığı mesaj mesaj izlemek, kısa ekran kaydı için ideal.

**Kurstan pekiştirdiği:** Hafta 5'teki `1_google_adk_a2a` (A2A sunucusu, agent card, uzak ajanı çağırma) ve aynı işi farklı framework'lerde yazma fikri. Hafta 2'deki structured output. Yeni olarak öğrettiği: iki framework'ü protokol üzerinden konuşturmak, çok-ajanlı bir etkileşimi tekrarlı koşup istatistikle raporlamak, gizli bilgi sızıntısını ölçmek.

### Tech stack

| Katman | Seçim |
|---|---|
| Alıcı | Google ADK `LlmAgent`, A2A istemcisi olarak satıcıyı `RemoteA2aAgent` ile çağırır |
| Satıcı | Pydantic AI ajanı, A2A sunucusu olarak yayınlanır (`to_a2a()`; güncel API'yi dokümandan doğrula). Olmazsa satıcı da ADK ile yazılır, framework çeşitliliği README'de "next" olur |
| Hakem | Saf Python: her teklif structured output (`Offer(price, terms, accept: bool)`). Anlaşma fiyatı iki tarafın gizli sınırları içinde mi, kim ne kadar fazla değer aldı, kaç turda bitti, gizli sayı metinde geçti mi (regex) |
| Modeller | Groq: `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`. Her eşleşme iki rolde de koşulur |
| Koşucu | Asenkron, kaldığı yerden devam eden, 429'da bekleyen. Sonuçlar JSONL |
| Replay sitesi | Statik: tek `index.html` + vanilla JS, JSONL'den sıralama tablosu ve sohbet oynatıcı. GitHub Pages |

### 2 günlük plan

- **Gün 1, öğleden önce:** Kurstaki `a2a_demo/server.py`'yi temel alarak iki süreçli spike: satıcı A2A sunucusu ayakta, alıcı ona bir mesaj atıp structured yanıt alıyor. Ollama ile.
- **Gün 1, öğleden sonra:** Senaryo şeması (ürün, gizli sınırlar, maksimum tur), hakem ve metrikleri, testleriyle. Tam pazarlık döngüsü, tek senaryo.
- **Gün 2, öğleden önce:** Koşucu: 3-5 senaryo x 4 model x iki rol x birkaç tekrar. Önce küçük bir koşuyla çağrı sayısını ölç, toplamı Groq'un günlük limitine göre böl.
- **Gün 2, öğleden sonra:** Replay sitesi, README'de sonuç tablosu ve en ilginç 3 pazarlık, Pages.

### Riskler

- **A2A kütüphanelerinin sürümü.** Protokol ve SDK'lar hızlı değişiyor. Sürümleri `uv.lock` ile sabitle ve README'ye yaz.
- **Küçük örneklem.** Tekrar sayısı az olacak. Tabloda güven aralığı veya en azından n'yi göster, "kesin kazanan" iddiası kurma.
- **Kota.** Bir pazarlık 6-12 çağrı. Koşu birkaç güne yayılabilir; koşucu devam edebilir olduğu için sorun değil.

### Claude Code başlangıç promptu

```
New repo: two agents built with different frameworks negotiate over the A2A protocol,
and a deterministic referee scores the outcome. Read Project 2 (Handshake) in
GLOBAL_PROJECTS.md and the course reference at 5_agent_frameworks/1_google_adk_a2a.
First verify from current docs: how Google ADK consumes a remote A2A agent, and whether
Pydantic AI can expose an agent as an A2A server. Then do the Day 1 spike with Ollama
and propose the plan for the scenario schema, referee and metrics. TDD after I approve.
```

---

## 3. RepoAtlas: herhangi bir repoyu 60 saniyede anlamak

**Tek cümle:** `uvx repoatlas https://github.com/owner/repo` komutu, Deep Agents ile kurulmuş bir ajan başlatır. Ajan repoyu planlı şekilde keşfeder: ana ajan bir plan çıkarır, alt ajanlar modülleri inceler. Sonuçta Mermaid mimari şeması, "hangi dosyadan başlamalı" rehberi, istek akışı açıklaması ve 5 iyi ilk katkı önerisi içeren bir `ATLAS.md` üretilir.

**Viral kanca:** Her geliştiricinin yaşadığı "bu repoyu nereden okumaya başlayacağım" sorunu. Gönderi: "I pointed a Deep Agent at FastAPI, LangGraph and Supabase repos. Here are the architecture maps it drew." Ünlü repoların atlasları galeride durur; insanlar kendi reposunda dener. Maintainer'ları otomatik etiketleme yok; paylaşmak istersen elle ve nazikçe yap.

**Kurstan pekiştirdiği:** Hafta 4'teki Deep Agents (planlama, sanal dosya sistemi, sub-agent, skill), LangGraph state. Yeni olarak öğrettiği: büyük bir girdide context yönetimi (her dosyayı okumamak, neyi okuyacağını seçmek), alt ajanlara iş bölmek, çıktı kalitesini kontrol etmek (şemadaki her modül repoda gerçekten var mı?).

### Tech stack

| Katman | Seçim |
|---|---|
| Ajan | Python, `deepagents` (LangChain), `langchain-groq`. Ana ajan + 2 alt ajan (`module-reader`, `diagram-writer`) |
| Repo erişimi | `git clone --depth 1` geçici klasöre. Tool'lar: `tree(path, depth)`, `read_file(path, start, end)`, `grep(pattern)`. Yalnızca okuma, klon klasörünün dışına çıkamaz, dosya boyutu ve toplam okuma bütçesi sınırlı |
| Doğrulama | Saf Python: Mermaid şemasındaki her düğüm ve `ATLAS.md`'deki her dosya yolu repoda var mı? Yoksa ajan bir kez düzeltmeye gönderilir, ikinci başarısızlıkta uyarıyla yazılır |
| Model | Groq `openai/gpt-oss-120b` (ana ajan), `openai/gpt-oss-20b` veya `llama-3.1-8b-instant` (alt ajanlar) |
| Çıktı | `ATLAS.md` (Mermaid, GitHub'da doğrudan render olur) |
| Dağıtım | PyPI + `uvx`. Galeri: ünlü 5-10 reponun atlası, GitHub Pages'te statik sayfa |

### 2 günlük plan

- **Gün 1, öğleden önce:** `deepagents`'ın güncel API'sini doğrula; özel tool'larla ve Groq modeliyle bir ajan kur. Klon ve okuma tool'ları, yol sınırı ve bütçe, testleriyle.
- **Gün 1, öğleden sonra:** Alt ajanlar ve `ATLAS.md` şablonu. Küçük bir repoda (kendi bir reponda) uçtan uca çalıştır.
- **Gün 2, öğleden önce:** Doğrulama adımı (yollar ve şema düğümleri), bütçe aşımında kısmi çıktı. Orta boy bir açık kaynak repoda dene, token ölç.
- **Gün 2, öğleden sonra:** CLI, README, GIF, galeri için 5 atlas, Pages, PyPI.

### Riskler

- **Büyük repolar.** Okuma bütçesi ve `tree` derinliği sınırı şart. Monorepo'larda `--path` parametresiyle alt klasör seçilebilir.
- **Yanlış mimari iddiası.** Doğrulama adımı uydurulmuş dosyayı yakalar ama yanlış yorumu yakalamaz. README'de "bir başlangıç haritası, gerçek kaynak kod" uyarısı.
- **Lisans.** Galeriye yalnızca açık kaynak lisanslı repoların atlaslarını koy; kod alıntısı yerine dosya yolu ve kısa açıklama kullan.

### Claude Code başlangıç promptu

```
New repo: a CLI that runs a LangChain Deep Agent over any GitHub repository and writes
ATLAS.md with a Mermaid architecture diagram and an onboarding guide. Read Project 3
(RepoAtlas) in GLOBAL_PROJECTS.md. First verify the current deepagents API from docs:
custom tools, sub-agents and using a Groq model via langchain-groq. Then propose the
Day 1 plan: read-only repo tools with path jail and read budget, sub-agents, and the
deterministic verification step. TDD after I approve.
```

---

## Önerilen sıra

1. **Clickthrough.** Kurstaki referans koda en yakın olanı, en hızlı biten ve en görsel sonucu veren. Ekran kaydı kendiliğinden ilgi çekiyor.
2. **RepoAtlas.** Geliştiricilerin en çok deneyeceği ve yıldız vereceği proje. Galeri sayesinde lansmandan sonra da trafik getirir.
3. **Handshake.** Ölçülmüş sonuç tablosu ile en çok tartışma yaratacak olan. Koşusu birkaç güne yayılabileceği için arka planda ilerlesin.

Mülakat açısından: Clickthrough "agent evaluation ve kendi işini doğrulama", Handshake "multi-agent ve A2A", RepoAtlas "context engineering ve büyük girdi" sorularına cevap.

## LinkedIn gönderi kalıbı (global)

- İngilizce ilk satır: sonuç ya da sayı ("I made two LLMs negotiate 100 times.").
- 20-30 sn ekran kaydı, link ilk yorumda, GitHub reposu README'de tek komutla çalışıyor olmalı.
- Gövdede 3 madde: ne yapıyor, hangi framework ve protokolle, en şaşırtıcı bulgu veya ne işe yaramadı.
- Kullandığın framework'leri ve kursu etiketle (Google ADK, LangChain, Pydantic AI, Playwright); framework toplulukları yeniden paylaşabiliyor.
- Aynı içeriği X ve Reddit'te (r/LocalLLaMA, r/LangChain) de paylaş; global erişim çoğunlukla oradan gelir.
