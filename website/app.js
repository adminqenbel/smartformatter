// QenBel Smart Formatter — Interactive Web Experience

document.addEventListener('DOMContentLoaded', () => {
  const btnFront = document.getElementById('btnDemoFront');
  const btnBack = document.getElementById('btnDemoBack');
  const origTitle = document.getElementById('demoOrigTitle');
  const formatTitle = document.getElementById('demoFormatTitle');
  const checksumToggle = document.getElementById('checksumToggle');
  const downloadBtn = document.getElementById('downloadBtn');

  // Interactive Front / Back Side Switcher in Hero Demo
  if (btnFront && btnBack) {
    btnFront.addEventListener('click', () => {
      btnFront.classList.add('active-front');
      btnBack.classList.remove('active-back');
      if (origTitle) origTitle.textContent = 'ORIGINAL CAPTURE (FRONT)';
      if (formatTitle) formatTitle.textContent = 'FORMATTED & PRINT-READY (FRONT)';
    });

    btnBack.addEventListener('click', () => {
      btnBack.classList.add('active-back');
      btnFront.classList.remove('active-front');
      if (origTitle) origTitle.textContent = 'ORIGINAL CAPTURE (BACK)';
      if (formatTitle) formatTitle.textContent = 'FORMATTED & PRINT-READY (BACK)';
    });
  }

  // SHA-256 Checksum Display / Copy
  if (checksumToggle) {
    checksumToggle.addEventListener('click', () => {
      const sha256 = 'SHA-256: 8c3e60ba791986427fc7e1cb2f57639c071dbe41829e5a840916ffb543781289';
      navigator.clipboard.writeText(sha256).then(() => {
        const originalText = checksumToggle.textContent;
        checksumToggle.textContent = 'Copied to Clipboard!';
        setTimeout(() => {
          checksumToggle.textContent = originalText;
        }, 2000);
      }).catch(() => {
        alert(sha256);
      });
    });
  }

  // Download Trigger feedback
  if (downloadBtn) {
    downloadBtn.addEventListener('click', () => {
      console.log('Initiating QenBel Smart Formatter download...');
    });
  }
});
