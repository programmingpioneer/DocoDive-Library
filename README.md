<div align="center">

# ⚡ DOCODIVE — The Cloud-Native Programming Vault
### *Free Knowledge • Pure Discipline • Built by Pioneers*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0%2B-lightgrey?style=for-the-badge&logo=flask&logoColor=black)](https://flask.palletsprojects.com/)
[![TiDB](https://img.shields.io/badge/TiDB-Cloud-ff69b4?style=for-the-badge&logo=tidb&logoColor=white)](https://tidbcloud.com/)
[![Brevo](https://img.shields.io/badge/Brevo-CRM_%26_Email-0B69FF?style=for-the-badge&logo=brevo&logoColor=white)](https://www.brevo.com/)
[![Cloudflare R2](https://img.shields.io/badge/Storage-Cloudflare_R2-F38020?style=for-the-badge&logo=cloudflare&logoColor=white)](https://www.cloudflare.com/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

> **Executive Summary:** DocoDive is a fully scalable, cloud-native open-source digital library engineered to distribute programming literature without infrastructure cost barriers. Utilizing serverless architecture, object storage decoupling, and enterprise-grade transactional messaging, it bridges the gap between high-performance web engineering and open access.

</div>

---

## 🎯 Project Overview & Objectives

Traditional digital libraries suffer from heavy server loads, costly storage bottlenecks, and weak security. **DocoDive** solves these engineering challenges through a modern decoupled micro-service approach:

* **Zero Cost Scaling:** Built entirely on serverless and edge cloud tiers to handle user traffic spikes natively.
* **Rigorous Data Integrity:** Enforces strict user session handling, profile verification, and community moderation workflows.
* **Production-Grade Security:** Implements scrypt password hashing, secure environment variables, and strict form validation gates.

> 🌐 **Experience It Live:** Don't just read the code—test out the fully deployed production platform right now: [🔗 Launch DocoDive Live](https://docodive-library.onrender.com/)

---

## 🛠️ Core Engineering Systems

| Subsystem | Technology Used | Implementation Purpose |
| :--- | :--- | :--- |
| **Backend Core** | Python, Flask, Werkzeug | RESTful routing, session management, secure credential hashing. |
| **Primary Database** | TiDB Serverless (MySQL Compatible) | Distributed relational storage with auto-scaling capabilities. |
| **Asset Storage** | Cloudflare R2 (S3-Compatible) | High-speed, zero-egress fee PDF binary storage. |
| **Messaging & CRM** | Brevo API | Transactional email delivery (verification/reset tokens) & live support routing. |
| **Frontend UI** | Bootstrap 5, Jinja2, AJAX | Responsive cross-device layout with dynamic asynchronous page components. |

---

## 🚀 Evolution: From a Simple Library to a Complete Community Platform

Every feature below was built incrementally, turning DocoDive into a robust, self‑moderating ecosystem. Here’s what we’ve shipped:

### 📚 Core Library Foundation
- **Unlimited PDF Uploads** – Admins and users can upload programming books with automatic category detection and duplicate checking.
- **Powerful Search & Filters** – Search by title, author, category, or language; live AJAX suggestions.
- **Book of the Day** – A fresh recommendation every 24 hours, generated dynamically.
- **Personalized Recommendations** – Based on user favorites and download history.
- **Favorites, History & Reviews** – Readers build their own library, track downloads, and leave star ratings with comments.
- **Read Online** – Embedded PDF viewer for instant access.

### 🔐 Identity & Security
- **Email Verification** – Beautiful verification emails via Brevo; accounts activated with one click.
- **Forgot Password Flow** – Inline AJAX‑based code entry followed by a secure tokenised reset link.
- **Streaks & Points** – Gamified daily login streaks and points for community activity.
- **User Profiles** – Custom avatars, bios, social links; stats like uploads, reviews, favorites.
- **First & Last Name Enforcement** – Mandatory fields during signup for a clean user audit trail.

### 👑 Official Community Account & Moderation
- **Blue Verified Tick (✔️)** – A dedicated official account, set by super‑admins, displays a verification badge everywhere (navbar, reviews, comments, leaderboard, notifications).
- **Clickable Official Profile** – Only the official account’s name links to its public profile, highlighting its authority.
- **Community Moderation Panel** – `/moderation` route accessible to admins and the official account. Displays recent reviews and comments in a table with inline delete and official reply options.
- **Inline Moderation on Book Pages** – Admins and the official account can delete any review or discussion comment and reply officially without leaving the page.
- **Leaderboard Integrity** – Official accounts are excluded from the leaderboard; their personal stats (uploads, points) are hidden on their profile page, keeping the competition fair for standard users.

### 💬 Live Chat & CRM Integration
- **Brevo Conversations Widget** – Built‑in live chat that captures visitor identity via a pre‑chat form (name & email) before the conversation begins, automatically saving them as contacts in your Brevo CRM.
- **No Anonymous Chats** – Every support request is linked to a real identity, improving support team efficiency.

### 🧠 Intelligent Automation
- **AI‑Enhanced Metadata** – Optional Gemini integration automatically improves book titles, author names, and descriptions during upload.
- **Automatic Category Detection** – PDF text analysis assigns the correct category without manual input.
- **Duplicate Book Detection** – Fuzzy matching prevents identical books from being uploaded twice.

### 📊 Dashboard & Analytics
- **Admin Dashboard** – Real‑time stats on books, users, admins, and categories; pending book counts; charts for library overview and category distribution.
- **Recent Uploads & Login Logs** – Super‑admins can monitor activity and audit login attempts.
- **Super‑Admin User Management** – Create, edit, or delete admin accounts directly from the dashboard.

---

## 🧠 System Workflow & Logic

1. **Onboarding:** User registers with First Name, Last Name, and Email $\rightarrow$ System triggers an asynchronous verification dispatch via Brevo.
2. **Access Control:** Verified users authenticate $\rightarrow$ Session tokens map directly to database states.
3. **Discovery & Retrieval:** Real-time search filters query TiDB $\rightarrow$ Client fetches metadata asynchronously via AJAX.
4. **Binary Delivery:** PDF downloads route directly through Cloudflare R2 object storage with progress tracking.
5. **Community Engagement:** Users leave reviews or upload documents $\rightarrow$ Submissions enter a pending moderation queue awaiting administrator approval.

---

## 📸 System Visual Preview

### 🛠️ Administrative Control Dashboard

<p align="center">
  <a href="https://docodive.programmingpioneer.com" target="_blank">
    <img src="static/Preview/Preview.png" alt="DocoDive Dashboard" width="70%" hight="70%" style="border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.3);">
  </a>
</p>
<p align="center">
  <i>Click the image above to explore the live dashboard.</i><br>
  Manage books, users, reviews, and official community settings from a single powerful interface.
</p>

## 🗺️ Project Roadmap

- [x] **Official Verified Badges & Profiles**
- [x] **Community Moderation Panel**
- [x] **Pre-Chat Form CRM Integration**
- [ ] **Full‑text Search Engine Integration** – Native Elasticsearch or TiDB advanced text indexing.
- [ ] **Automated Donation & Sponsorship Module** – Community monetization gateway.
- [ ] **AI-Powered Semantic Recommendations** – Smart book suggestions driven by language models.

---

## 🤝 Contributing

We welcome contributions that push the boundaries of open‑source education:

1. **Fork** the repository
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Commit your changes** (`git commit -m 'Add some amazing feature'`)
4. **Push to the branch** (`git push origin feature/amazing-feature`)
5. **Open a Pull Request**

---

## ⚡ Quick Start & Deployment Guide

### 📦 System Prerequisites
- Python **3.10+** and pip
- Git
- Active accounts on [TiDB Cloud](https://tidbcloud.com), [Cloudflare R2](https://developers.cloudflare.com/r2/), and [Brevo](https://www.brevo.com/)
- (Optional) [Google Gemini API](https://ai.google.dev/) key for AI-enhanced book metadata

### 🚀 Local Installation Steps

1. **Clone the Repository**
   ```bash
   git clone [https://github.com/programmingpioneer/DocoDive-Library.git](https://github.com/programmingpioneer/DocoDive-Library.git)
   cd docodive

---
## 👤 About the Creator

<div align="center">

### **Sufyan Khan**
*Full-Stack Engineer & Open-Source Builder*

</div>

Yo! I’m **Sufyan Khan** — a developer who decided that instead of just waiting around for a degree to start building, I was going to roll up my sleeves and ship real production code. 

Fresh out of my FSc studies, I architected and built **DocoDive** entirely from scratch. We're talking serverless databases, cloud-native object storage, automated email pipelines, and real security infrastructure—all engineered to solve a real problem without spending a single dollar on server costs.

My mindset is simple: **Pure Discipline.** No excuses, no shortcuts, just relentless execution. If you want something built right, you build it yourself.

> *"From studying FSc textbooks to architecting cloud-native systems—this is just chapter one."*

<div align="center">

[![GitHub Profile](https://img.shields.io/badge/GitHub-Sufyan_Khan-black?style=for-the-badge&logo=github&logoColor=white)](https://github.com/yourusername)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://linkedin.com/in/yourusername)

</div>