# 小技产品介绍官网 Image 生成说明

## 项目信息

- 产品名称：小技
- 产品定位：面向无人机学习、练习答题、AI 智能中心、招聘服务的产品应用
- 官网域名：xiaoji.caacyj.com
- 备案号：鄂ICP备2025105924号-3A
- 目标：先生成产品介绍官网视觉稿，再按视觉稿开发静态官网

## 参考素材

以下真实 App 截图作为 Image 生成参考图使用：

- `../assets/app-login.png`：登录页
- `../assets/app-practice.png`：练习页
- `../assets/app-practice-start.png`：练习开始页
- `../assets/app-quiz-state-01.png`：答题页状态 01
- `../assets/app-quiz-state-02.png`：答题页状态 02
- `../assets/app-ai-center.png`：智能中心页
- `../assets/app-jobs.png`：招聘页
- `./xiaoji-reference-board.png`：参考拼版，建议作为首选输入图

## Prompt 01：官网整页视觉稿

Use case: ui-mockup
Asset type: product landing page design mockup for implementation
Primary request: Generate a polished full-page website mockup for a Chinese product introduction website named "小技".
Input images: Use the provided reference board and app screenshots as product UI references. Preserve the real mobile app screenshot feeling, but do not need to copy every pixel.
Product context: 小技 is an app product for drone learning, exam practice, AI-assisted study, question review, intelligent center, and recruitment/job information.
Audience: students learning drone operation, training institutions, and operators who manage learning services.
Style/medium: high-fidelity web UI mockup, modern education technology and practical SaaS style, clean and professional.
Composition/framing: desktop web page, 1440px-wide layout. First viewport must clearly show the product name "小技", a short product positioning statement, primary action buttons, and a composition of 3 to 5 mobile app screens in phone frames. Below the hero, show sections for product positioning, workflow diagrams, real app screens, and application scenarios.
Color palette: fresh but restrained technology palette; white background, light cyan and blue accents, small amount of green and orange for highlights. Avoid a one-color blue/purple gradient look.
Layout requirements: no marketing-only empty hero; the product and app screens must be visible immediately. Use dense but readable information structure. Cards should be subtle with small border radius. Use real screenshot-style phone mockups.
Text (verbatim): "小技", "AI 学习与训练助手", "面向无人机学习、训练、考证的智能产品应用", "真实界面", "产品定位", "学习闭环", "AI 解析", "招聘服务".
Footer text (verbatim): "© 2026 小技", "鄂ICP备2025105924号-3A".
Constraints: Chinese website design; readable hierarchy; realistic app product introduction site; no excessive decorative blobs; no cartoon mascot; no fake brand logos; no watermark. Text in generated image can be approximate because final text will be implemented in HTML/CSS.
Avoid: purple-dominant gradient, dark-heavy cyberpunk style, stock photo people, large abstract illustrations, unreadable dense text, nested card-heavy layout, overly rounded pill UI.

## Prompt 02：首屏 Hero 主视觉

Use case: ui-mockup
Asset type: landing page hero visual
Primary request: Create a website hero visual for the product "小技", showing a professional product introduction page for a drone learning and AI practice app.
Input images: Use the app screenshots as references for phone screens. Use the intelligent center, practice, quiz result, and jobs screenshots as the main phone visuals.
Scene/backdrop: clean web hero area with light background, subtle grid or soft technical texture, no decorative orbs.
Subject: 3 to 5 smartphone mockups displaying app screens, arranged with depth but not chaotic. The product name "小技" and product line "AI 学习与训练助手" appear on the left.
Style/medium: high-fidelity web UI design, polished SaaS landing page, education technology, realistic mobile UI presentation.
Composition/framing: wide 16:9 hero section. Left side has headline and CTA area; right side has phone screen composition. Leave enough negative space for implementation.
Color palette: white, light cyan, deep blue, teal green, small orange accents.
Text (verbatim): "小技", "AI 学习与训练助手", "把学习、练习、解析、复盘和服务连接起来".
Constraints: product screens must be the dominant visual signal; no stock photography; no cartoon characters; no drone photo as the main subject unless subtle and secondary; no watermark.
Avoid: fake app screens unrelated to the reference, neon cyberpunk, purple gradient, large abstract SVG illustration look.

## Prompt 03：真实界面展示区

Use case: ui-mockup
Asset type: website section design
Primary request: Design a website section that showcases seven real mobile app pages for "小技".
Input images: Use all seven app screenshots as phone screen references.
Subject: A responsive grid of phone mockup cards, each with a short title and explanation.
Titles: "登录页", "练习页", "练习开始页", "答题状态 01", "答题状态 02", "智能中心页", "招聘页".
Style/medium: clean product documentation style with premium visual polish, suitable for implementation in HTML/CSS.
Composition/framing: desktop section, 3-column grid on desktop, 1-column on mobile. Phone frames are consistent and screenshots are cropped from the top.
Color palette: white cards, subtle borders, light blue-gray page background, restrained blue/green accents.
Constraints: each phone card must be readable and evenly aligned; avoid oversized shadows; avoid decorative clutter; no watermark.

## 开发落地建议

- 用 `xiaoji-reference-board.png` 或 Prompt 01 生成整页视觉稿。
- 用 Prompt 02 单独生成 Hero 主视觉参考。
- 用 Prompt 03 单独生成真实界面展示区参考。
- 生成图仅作为视觉方向，最终文字、备案号、链接必须由 HTML/CSS 实现，避免图片中文字不可控。
- 正式页面底部必须保留：
  - `© 2026 小技`
  - `鄂ICP备2025105924号-3A`
  - 备案链接：`https://beian.miit.gov.cn/#/Integrated/index`
