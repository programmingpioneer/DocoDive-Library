# DocoDive SEO guide — Roman Urdu

Tareekh: 7 November 2026. Yeh guide current local source aur Google ki official documentation par mabni hai. Is pass mein Search Console, analytics account, live pages, database ya staging inspect nahi kiye gaye. Is liye neeche code mein mojood cheez, source se milne wali kami, aur owner ko karna wala kaam alag bataya gaya hai. Ranking ya indexing ki guarantee nahi hoti. [Google Search Essentials](https://developers.google.com/search/docs/essentials)

## 1. Aapke project mein abhi kya mojood hai

| Cheez | Local source mein haal |
|---|---|
| Titles, descriptions, canonical, robots, Open Graph aur Twitter metadata | Shared public base template mein mojood |
| Preferred website address | `PUBLIC_SITE_URL` ka support hai; actual configured value inspect nahi ki |
| XML sitemap | `/sitemap.xml` index; pages aur approved books ke separate child sitemaps; books 5,000 URLs ke batches mein |
| Search/account exclusion | Specified search/filter variants, non-public endpoints aur errors ke liye `noindex` policy |
| Structured data | Home par WebSite/Organization; book detail par Book/Offer/BreadcrumbList; catalogue par CollectionPage/ItemList |
| Slug redirects | Missing/incorrect book slug ke liye permanent redirect ka code |
| Search verification aur analytics | Verification tags aur consent ke baad analytics load karne ka code; successful verification/traffic reporting unknown |

Source: [seo.py](../seo.py), [public base template](../templates/user/base.html), [book detail](../templates/user/book_detail.html), [privacy controls](../static/js/privacy.js). Code ka hona live indexing, traffic ya ranking ka saboot nahi hai.

## 2. Sab se pehle yeh source issues address karein

Yeh recommendations hain; is guide ke saath SEO behavior change nahi kiya gaya.

| Tarjeeh | Masla | Zaroori correction aur verification |
|---|---|---|
| P1 | Learning Hub template `request.base_url` use karta hai, jis se `?page=2` hat jata hai aur preferred origin bhi bypass hota hai | Shared canonical helper use karein; real hub template ko page 1, page 2 aur alternate request host ke saath render karke check karein |
| P1 | Out-of-range catalogue/home page numbers last page ka content dikha sakte hain, jabke canonical requested number rakhta hai | Invalid inputs par proper redirect ya error policy banayein; ek hi last page ke be-shumar self-canonical duplicates na banne dein |
| P1 | Invalid category se all-books content aa sakta hai, jabke raw category canonical mein rehti hai | Category normalize/validate karein aur valid destination ya clear error dein |
| P1 | Generic fallback lessons “Coming Soon” ke bawajood indexable allowlist aur sitemap generation mein aa sakte hain | Har available module ki content readiness check karein; unfinished modules ko sitemap se exclude aur public placeholder ko `noindex` karein |
| P2 | Kuch ItemList/breadcrumb addresses request host se bante hain | Metadata, schema, sitemap aur internal links mein preferred origin consistent karein |
| P2 | Category-based generated descriptions har book ki asal coverage se match karna zaroori nahi | Actual books check karke accurate summaries likhein; local inspection se affected live record count maloom nahi |

Relevant source: [learning_hub.html](../templates/user/learning_hub.html), [app.py](../app.py), [seo.py](../seo.py), [generic beginner](../templates/user/learn_universal/beginner.html), [generic intermediate](../templates/user/learn_universal/intermediate.html). Existing small SEO test fixture real hub canonical override ko cover nahi karta; template-level regression coverage bhi chahiye.

Paginated page 2 ko page 1 ki canonical dena sahi policy nahi. Har real page ka apna URL/canonical ho aur next/previous links real `<a href>` hon. [Google pagination guidance](https://developers.google.com/search/docs/specialty/ecommerce/pagination-and-incremental-page-loading)

## 3. Production domain ko ek jagah consistent rakhein

Is guide ke domain examples `https://docodive.programmingpioneer.com` use karte hain, jo pehle share ki gayi production information mein tha. Owner apna final preferred domain confirm kare.

- `PUBLIC_SITE_URL` ko final HTTPS origin ke mutabiq rakhein. Is ki value yahan check/change nahi ki gayi.
- Canonical, sitemap, Open Graph URL, structured data aur important internal links isi origin ko use karein.
- Duplicate host/protocol versions ke redirects owner verify kare. Localhost aur temporary Render addresses ko production sitemap ka preferred address na banayein.
- Book ka slug badlein to purana URL relevant new page par permanent redirect kare. Har purane/missing page ko homepage par na bhejein.

Google canonical signals ko evaluate karta hai; declared canonical ek preference hai. Sitemap aur canonical ek doosre ke khilaf addresses na dein. [Canonical URL guidance](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls)

## 4. Google Search Console owner setup

1. Apne Google account mein [Search Console](https://search.google.com/search-console/) open karein aur property add karein.
2. Exact HTTPS website ke liye URL-prefix property use kar sakte hain. Domain property chahiye to DNS verification karein; apne control wala relevant domain/subdomain use karein.
3. Verification method ke mutabiq owner khud DNS record ya site verification complete kare. Existing HTML tags se yeh assume na karein ke aapka current account verified hai.
4. Verification ke baad sitemap submit karein.
5. Credentials, OTP ya private account export chat mein bhejne ki zaroorat nahi.

[Google ownership verification instructions](https://support.google.com/webmasters/answer/9008080)

Sitemaps area mein `https://docodive.programmingpioneer.com/sitemap.xml` submit karein. Index aur child sitemaps ko successful fetch hona chahiye. Important new/updated pages ka sample URL Inspection mein inspect karein; har page ko baar baar submit karna content quality ka badal nahi. Sitemap discovery mein madad deta hai, indexing ki guarantee nahi. Sirf desired canonical, indexable URLs rakhein; expired signed PDF links, login URLs aur unfinished pages exclude karein. [Build and submit a sitemap](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)

## 5. Kaun se pages Search mein aane chahiye

| Page family | DocoDive ke liye recommended approach |
|---|---|
| Home, `/books`, meaningful category hubs | Public, complete aur indexable |
| `/book/<slug>/<id>` | Har approved resource ka permanent detail page primary search landing page ho |
| Beginner/intermediate/advanced/practice lessons | Substantial content ready ho to indexable |
| Reviews/community pages | Useful public content ho to consider karein; empty variants ko review karein |
| Internal searches, sort/filter duplicates | Deliberate canonical/noindex policy; har query ko separate landing page na banayein |
| Login, password recovery, settings, admin | Search landing pages nahi; authentication aur noindex policy barkarar |
| PDF/reader/download endpoints | Current app policy noindex rakhti hai; promotion aur linking permanent book-detail page par karein |
| 404/500 aur unavailable resources | Sahi error status; homepage ka HTML 200 response ke saath na dikhayein |

`robots.txt` crawling control karta hai; private data ki security authentication se hoti hai. `noindex` Google ko tab nazar aata hai jab woh response crawl kar sake. Sirf robots disallow ko reliable de-indexing na samjhein. [Google noindex guidance](https://developers.google.com/search/docs/crawling-indexing/block-indexing)

## 6. Keyword aur page planning

Pehle user ka sawal samjhein, phir us ka best jawab ek suitable page par dein. Neeche examples editorial suggestions hain; search-volume ya competition research ka claim nahi.

| Intent | Suggested query/theme | Suitable page |
|---|---|---|
| Library explore karna | free programming books | Home ya catalogue, distinct purpose ke saath |
| Python resources chunna | Python books for beginners | `/learn/python` |
| Python seekhna | Python variables and loops examples | Complete beginner lesson |
| Practice karna | Python practice exercises with answers | Python practice page |
| Ek specific book dhoondhna | exact title + author | Us book ka canonical detail page |
| IELTS skill improve karna | IELTS reading practice strategies | Relevant IELTS reading module |

Ek hi keyword ke liye bohat se near-identical pages na banayein. Existing Search Console queries se maloom karein ke users asal mein kya dhoondhte hain, phir page purpose improve karein. Category aur lesson ka difference saaf ho: hub resources choose karwaye, lesson sikhaye, practice kaam karwaye.

## 7. Har book page ka useful content

Apni editorial checklist mein yeh rakhein:

- Sahi title, author, language, category aur level; unknown detail ko invent na karein.
- Original summary: resource kis bare mein hai, kis learner ke liye hai aur kya prerequisite chahiye.
- Verified topics, edition/date jab available hon, aur source/attribution ki clear information.
- Relevant cover, clear Preview/Read/Download labels aur functioning actions.
- Meaningful related resources aur real reader feedback.
- Jo resource distribute karne ki authorization ho wohi publish/promote karein; rights-reporting link accessible rahe.

Example summary structure: “Yeh handbook Python ke naye learners ke liye variables aur loops ko worked examples se samjhati hai. Basic computer use ka tajurba kafi hai. Download se pehle contents aur edition check karein.” Is example ko har book par paste na karein; sirf verified coverage likhein.

## 8. Learning Hub content ko kis tarah behtar karein

Har complete track mein clear learning outcome, prerequisites, correct examples, practical task, expected result aur next lesson link dein. Content ko creator/reviewer ke naam aur relevant background ke saath maintain karein. Update date tab badlein jab meaningful correction/update ho. Filler se word count barhana zaroori nahi; student ka sawal poora hal hona zaroori hai. [People-first content guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content)

Misal: “Python loops” lesson mein `for` aur `while` ka farq, runnable examples, common mistake, chhota exercise aur explained solution ho. Practice page par task completion se user ko apni progress samajh aaye. Sirf generic introduction aur books ki list learning lesson ka poora badal nahi.

## 9. Titles, descriptions aur internal links

Recommended title examples:

- Home: `Free Programming Books & Learning Resources | DocoDive`
- Python hub: `Python Books & Learning Paths | DocoDive`
- Lesson: `Python Beginner Guide: Variables & Loops | DocoDive`
- Book: `[Actual Book Title] by [Actual Author] | DocoDive`

Title page ko accurately describe kare, concise ho aur repeated keywords se bhara na ho. Page par clear main heading aur logical subheadings hon. Google apni title presentation choose kar sakta hai. [Title-link guidance](https://developers.google.com/search/docs/appearance/title-link)

Meta description ka example: “Explore Python books, beginner guides and practical exercises. Preview resources and choose the right next step for your learning.” Har page ke mutabiq likhein. Exact character count ko ranking rule na samjhein; Google snippet page text se bhi bana sakta hai. [Snippet guidance](https://developers.google.com/search/docs/appearance/snippet)

Links mein destination samajh aaye: “Python practice exercises” achha label hai. Icons ke saath accessible text/label rahe. Important books ke standalone detail links hon; sirf JavaScript popup se unhein discover karne par depend na karein. Home → hub → lesson → relevant book ka natural path banayein. [SEO starter guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide)

## 10. Structured data ko honest rakhein

Existing schema ko actual visible content se match karke validate karein. Unknown author, fake reviews, inflated user counts, unverified price/availability ya unsupported course claims add na karein. Valid markup bhi special Search appearance ki guarantee nahi. [Structured data policies](https://developers.google.com/search/docs/appearance/structured-data/sd-policies)

[Rich Results Test](https://search.google.com/test/rich-results) se supported features inspect karein. Book JSON-LD ka hona Google Book Actions mein automatic participation nahi deta; Google ka us feature ke liye separate provider/feed process hai. [Book Actions documentation](https://developers.google.com/search/docs/appearance/structured-data/book)

Breadcrumbs user ko page ki jagah samjhayein aur unke labels/URLs actual site hierarchy se match karein. [Breadcrumb guidance](https://developers.google.com/search/docs/appearance/structured-data/breadcrumb)

## 11. Speed aur loading ki measurement

Core Web Vitals ke good targets:

| Metric | Target | Matlab |
|---|---|---|
| LCP | 2.5 seconds ya kam | Main visible content kitni jaldi aata hai |
| INP | 200 milliseconds ya kam | Interaction ka response |
| CLS | 0.1 ya kam | Layout kitna jump karta hai |

Yeh real-user experience measures hain. PageSpeed Insights mein field data available ho to 75th-percentile results dekhein; kam traffic par field data missing ho sakta hai. Lab test ko live real-user performance ka certificate na samjhein. [Core Web Vitals](https://developers.google.com/search/docs/appearance/core-web-vitals), [PageSpeed Insights measurement](https://developers.google.com/speed/docs/insights/v5/about)

DocoDive ke liye recommended optimization order: responsive cover sizes/compression; image space pehle reserve karna; below-fold covers lazy-load karna; heavy scripts ko zaroorat par load karna; database queries/pagination ki measurement; public assets ki appropriate caching. Pehle bottleneck measure karein. Skeletons page layout match karein aur content ready hone par hat jayein; extra animation/wait ko speed improvement na samjhein.

Cover ko real `<img>` mein relevant alt text ke saath rakhein, maslan “[Book title] cover”. Decorative icons ke alt mein keywords na bharein. [Image SEO guidance](https://developers.google.com/search/docs/appearance/google-images)

## 12. Mobile, Light/Dark aur language

Recommended manual checks: 360/390 px phone, 768 px tablet, normal desktop aur 4K; dono appearances; zoom; keyboard navigation. Text readable rahe, buttons overlap na hon, horizontal overflow na ho aur important content phone par bhi available ho. New visitor ko Light default mile; deliberate Dark selection remember ho.

Agar baad mein proper Urdu/English versions publish karein to separate stable URLs, complete translations aur relevant `hreflang` mapping plan karein. Sirf automated language swap ko full multilingual SEO setup na kahein. [Multilingual site guidance](https://developers.google.com/search/docs/specialty/international/managing-multi-regional-sites)

## 13. Promotion aur latest AI-search guidance

Useful original exercises, curated reading paths aur accurate book summaries ko relevant developer/education communities mein share karein. Authors ya educational maintainers ko resource genuinely useful ho to inform karein. Paid ranking links, bulk spam comments, artificial link networks aur fake reviews se bachain. Large-scale low-value copied/generated pages bhi strategy nahi. [Google spam policies](https://developers.google.com/search/docs/essentials/spam-policies)

Google ke mutabiq AI Overviews/AI Mode ke liye extra special SEO requirements nahi. Accessible, useful, trustworthy content aur normal SEO foundations par kaam karein. Kisi special AI file ya markup ko appearance ki guarantee na samjhein. [AI features and your website](https://developers.google.com/search/docs/appearance/ai-features)

## 14. Reporting: har hafta kya dekhna hai

Search Console mein pages/queries ke clicks, impressions, CTR aur average position dekhein. CTR clicks ko impressions se divide karke milta hai. Similar date ranges compare karein; ek din ke movement par faisla na karein. Queries aur landing pages ka purpose dekh kar low-performing content ko improve karein. [Search Console aur Analytics ka farq](https://developers.google.com/search/docs/monitor-debug/google-analytics-search-console)

Apni working sheet mein week, URL, main query, impressions, clicks, CTR, indexed status aur action likhein. Sath sitemap failures, unexpected noindex, server errors aur unavailable book actions note karein. Downloads/reading-starts jaise product events tab report karein jab unki actual instrumentation aur consent behavior verify ho; existing GA loader ko successful event reporting na samjhein.

## 15. Suggested 30-day implementation order

Yeh work schedule hai, ranking ka promised timeframe nahi.

| Waqt | Kaam | Completion evidence |
|---|---|---|
| Din 1–3 | Preferred domain, Search Console ownership, sitemap aur source ke P1 issues | Correct canonical samples, verified property, successful sitemap fetch |
| Din 4–7 | Important book pages aur one complete learning track audit | Accurate unique summaries; broken actions/links ki correction list |
| Hafta 2 | Student-focused lessons, internal links, image/schema validation | Complete examples/tasks, standalone book links, supported schema checks |
| Hafta 3 | Mobile/performance bottlenecks measure aur address | Before/after measured results; no visual/action regressions |
| Hafta 4 | Search data review aur relevant promotion | Page/query comparison aur next prioritized content tasks |

## 16. Publish karne se pehle final checklist

- [ ] Important public pages anonymously load hoti hain aur intended status deti hain.
- [ ] Canonical domain consistent hai; page 2 ka canonical page 2 hai.
- [ ] Invalid category/page values duplicate search pages nahi banate.
- [ ] Sitemap ke index aur children fetch hote hain; unfinished/private/expired URLs excluded hain.
- [ ] Book metadata aur visible content accurate hain; read/download actual resource kholte hain.
- [ ] Titles, descriptions aur schema relevant hain; real content par mabni hain.
- [ ] Phone, desktop, Light aur Dark mein important text/actions usable hain.
- [ ] Search Console/analytics status owner ne khud verify kiya hai.
- [ ] Report mein measured results aur pending checks saaf alag hain; fake SEO scores/ranking promises nahi.

Is pass mein default appearance local code mein update hua hai. SEO findings aur yeh implementation plan delivery hain; upar diye SEO corrections, Search Console setup aur production checks abhi completed implementation ke taur par claim nahi kiye gaye.
