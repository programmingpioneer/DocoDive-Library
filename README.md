# 📚 DocoDive – Free Knowledge, Pure Discipline

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-2.0%2B-lightgrey?logo=flask)
![MySQL](https://img.shields.io/badge/MySQL-5.7%2B-orange?logo=mysql&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

A **full‑stack digital library** and **eBook management platform** built with **Flask & MySQL**.  
Upload, browse, read, and share programming PDFs – all wrapped in a modern, responsive UI with **AJAX‑powered password reset**, **professional email templates**, and a robust **admin panel**.

---

## 📖 Table of Contents
- [✨ Features](#-features)
- [🧠 How It Works](#-how-it-works)
- [🧰 Tech Stack](#-tech-stack)
- [🚀 Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Variables](#environment-variables)
  - [Database Setup](#database-setup)
  - [Running the App](#running-the-app)
- [📸 Screenshots](#-screenshots)
- [🚀 Upcoming Features (Roadmap)](#-upcoming-features-roadmap)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)
- [📬 Contact](#-contact)

---

## ✨ Features

### **📚 Public Library**
- **Browse & Search** – Hundreds of programming PDFs in a responsive grid.  
- **Smart Suggestions** – Real‑time autocomplete as you type in the search bar.  
- **Filter by Category, Author, Language** – Narrow down results instantly.  
- **Live Category Counts** – Each category shows how many approved books it contains (polled every 30s).  
- **Book Carousel** – Featured titles with navigation indicators.  
- **Book Detail Page** – View title, author, description, cover image, language, and user reviews.

### **👤 User Accounts**
- **Secure Registration & Login** – Username, email, and password with email verification.  
- **AJAX Forgot Password** – Enter your email → 4‑digit code boxes appear inline → verify code → reset link sent.  
  *No page reloads, no ugly redirects, just smooth interaction.*  
- **Favourites** – Save books you love, access them from your profile.  
- **Download History** – Every PDF you download is tracked for later reference.  
- **Reviews & Ratings** – Give a 5‑star rating and write a comment on any book.

### **🛠️ Admin Panel**
- **Upload PDFs** – Choose a PDF file, optional cover image, and category.  
- **AI Metadata Enhancement** (optional) – Uses Google Gemini to polish title, author, and description.  
- **Approve / Reject** – Super‑admin can review pending books before they appear publicly.  
- **Edit & Delete** – Replace PDFs, update cover images, change metadata.  
- **Analytics Dashboard** – Total books, downloads, users, and recent uploads.  
- **Admin Management** – Add, edit, delete other admin accounts (super‑admin only).  
- **Login Logs** – Track every admin login attempt with IP and timestamp.

### **🎨 UI / UX**
- **Sticky Navbar** – Always accessible, even when scrolling long lists.  
- **Back‑to‑Top Button** – Smoothly returns to the top of the page.  
- **Dark Mode** – Elegant dark colour scheme with refined contrast.  
- **Fully Responsive** – Optimised for mobile, tablet, and desktop screens.  
- **Professional Email Templates** – Beautiful HTML emails for verification, password reset, and admin notifications.

### **🔐 Security & Validation**
- **Signup Validation** – Email format check, disposable domain blocking, username (3‑20 alphanumeric), password minimum length.  
- **Duplicate Prevention** – No two users can share the same email or username.  
- **Password Hashing** – All passwords stored using Werkzeug’s secure hashing (pbkdf2:sha256).  
- **Session Management** – Users and admins have separate session scopes.

---

## 🧠 How It Works

1. **User Registration** – A new user signs up with a valid email. A verification link is emailed.  
2. **Email Verification** – Clicking the link activates the account; the user can now log in.  
3. **Library Browsing** – After login, the home page shows all approved books with search, filters, and live category counts.  
4. **Book Interaction** – Click a book to view details, download the PDF, read online, add a review, or save it to favourites.  
5. **Forgot Password (AJAX Flow)**  
   - User clicks “Forgot Password?” on the login page.  
   - Enters email → receives a **4‑digit code** (stored in `password_resets` table with a 10‑minute expiry).  
   - Code boxes appear on the same page; user types the code and clicks “Verify”.  
   - On success, a **reset link** is emailed; user clicks it to set a new password.  
6. **Admin Uploads** – Super‑admins upload PDFs via the admin panel. The book stays in “pending” until approved.  
7. **Approval & Publishing** – Once approved, the book appears in the public library. Category counts update automatically.

---

## 🧰 Tech Stack

| Layer          | Technology |
|----------------|------------|
| **Backend**    | Flask (Python) – routes, forms, sessions |
| **Database**   | MySQL – relational storage for books, users, categories, etc. |
| **Frontend**   | HTML5, CSS3, JavaScript (AJAX, Fetch API) |
| **Email**      | Flask‑Mail + SMTP (Gmail, etc.) |
| **PDF Handling** | PyPDF2 for metadata and text extraction |
| **AI (optional)** | Google Gemini API for title/author enhancement |
| **Icons**      | Bootstrap Icons |
| **Authentication** | Werkzeug password hashing (pbkdf2:sha256) |
| **Deployment** | Render, Heroku, PythonAnywhere, or any WSGI server |

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.8+** with pip
- **MySQL** server running (local or remote)
- **SMTP credentials** – a Gmail account with an **App Password** is recommended
- (Optional) **Google Gemini API key** if you want AI metadata

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/docodive.git
   cd docodive