document.addEventListener("DOMContentLoaded", () => {
    // ==========================================
    //  PREVIEW MODAL + DOWNLOAD WITH PROGRESS
    //  (Responsive – works on all devices)
    // ==========================================

    // 1. POPUP OPENING LOGIC (Image click)
    const previewBtns = document.querySelectorAll('.preview-btn');
    
    previewBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            // Grab data directly from the image container
            const title = this.getAttribute('data-title');
            const level = this.getAttribute('data-level');
            const link = this.getAttribute('data-link');
            const author = this.getAttribute('data-author');
            const desc = this.getAttribute('data-desc');
            const img = this.getAttribute('data-img');
            const lang = this.getAttribute('data-lang');

            // Inject into modal
            document.getElementById('modalTitle').textContent = title;
            document.getElementById('modalLevel').textContent = level;
            document.getElementById('modalLang').textContent = (lang && lang !== 'None') ? lang : "English";
            document.getElementById('modalAuthor').textContent = (author && author !== 'None') ? author : "Admin";
            document.getElementById('modalDesc').textContent = (desc && desc !== 'None') ? desc : "No description available.";
            
            // Set the target URL for the custom download logic
            document.getElementById('modalDownloadBtn').setAttribute('data-file-url', link);
            
            // Reset Progress Bar UI
            document.getElementById('downloadProgressContainer').classList.add('d-none');
            document.getElementById('modalDownloadBtn').classList.remove('d-none');
            document.getElementById('downloadProgressBar').style.width = '0%';
            document.getElementById('downloadPercent').textContent = '0%';

            // Handle Cover Image inside modal
            const imgContainer = document.getElementById('modalImageContainer');
            if (img && img !== "None" && img.trim() !== "") {
                imgContainer.innerHTML = `<img src="${img}" class="img-fluid shadow-sm w-100" style="object-fit: cover; max-height: 400px; border-radius: 15px;" alt="Cover">`;
            } else {
                imgContainer.innerHTML = `
                    <div class="bg-light d-flex justify-content-center align-items-center" style="height: 350px; border-radius: 15px;">
                        <i class="bi bi-journal-code text-primary" style="font-size: 6rem;"></i>
                    </div>`;
            }

            // Show popup (Bootstrap modal)
            const pdfModal = new bootstrap.Modal(document.getElementById('pdfPreviewModal'));
            pdfModal.show();
        });
    });

    // 2. CUSTOM DOWNLOAD WITH PROGRESS BAR LOGIC
    const downloadBtn = document.getElementById('modalDownloadBtn');
    
    if(downloadBtn) {
        downloadBtn.addEventListener('click', function() {
            const fileUrl = this.getAttribute('data-file-url');
            if (!fileUrl) return;

            // Swap Button for Progress Bar
            this.classList.add('d-none');
            const progressContainer = document.getElementById('downloadProgressContainer');
            progressContainer.classList.remove('d-none');
            
            const progressBar = document.getElementById('downloadProgressBar');
            const progressPercent = document.getElementById('downloadPercent');

            // Fetch file using AJAX to track progress
            let xhr = new XMLHttpRequest();
            xhr.open('GET', fileUrl, true);
            xhr.responseType = 'blob'; // We need a blob to save it as a physical file

            xhr.onprogress = function(e) {
                if (e.lengthComputable) {
                    let percentComplete = Math.round((e.loaded / e.total) * 100);
                    progressBar.style.width = percentComplete + '%';
                    progressPercent.textContent = percentComplete + '%';
                }
            };

            xhr.onload = function() {
                if (xhr.status === 200) {
                    // File downloaded to memory, now force the browser to save it
                    const blob = xhr.response;
                    const downloadUrl = window.URL.createObjectURL(blob);
                    
                    // Extract filename from URL or give default
                    let filename = fileUrl.substring(fileUrl.lastIndexOf('/') + 1);
                    if(!filename || filename.length < 3) filename = "DocoDive_Resource.pdf";

                    // Create invisible anchor tag to trigger local system save
                    const a = document.createElement('a');
                    a.style.display = 'none';
                    a.href = downloadUrl;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    
                    // Cleanup
                    window.URL.revokeObjectURL(downloadUrl);
                    a.remove();

                    // UI feedback
                    progressPercent.textContent = "Complete!";
                    progressBar.classList.remove('progress-bar-animated');
                    
                    setTimeout(() => {
                        progressContainer.classList.add('d-none');
                        downloadBtn.classList.remove('d-none');
                    }, 3000);
                }
            };

            xhr.send();
        });
    }
});