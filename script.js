// Reactive / haptic feedback for header interactions (nav links, logo, CTA, toggle)
(function () {
  const tappable = document.querySelectorAll('.nav-links a, .nav-actions .btn, .nav-toggle, .logo, .hero-actions .btn');
  const buzz = () => { if (navigator.vibrate) navigator.vibrate(12); };
  tappable.forEach(el => {
    el.addEventListener('touchstart', () => { el.classList.add('pressed'); buzz(); }, { passive: true });
    el.addEventListener('touchend', () => el.classList.remove('pressed'));
    el.addEventListener('touchcancel', () => el.classList.remove('pressed'));
    el.addEventListener('mousedown', () => el.classList.add('pressed'));
    el.addEventListener('mouseup', () => el.classList.remove('pressed'));
    el.addEventListener('mouseleave', () => el.classList.remove('pressed'));
  });
})();

// Products drawer — slide open to reveal remaining product categories
(function () {
  const btn = document.getElementById('viewAllProductsBtn');
  const label = document.getElementById('viewAllProductsLabel');
  const drawer = document.getElementById('productsDrawer');
  if (!btn || !drawer) return;
  let open = false;
  btn.addEventListener('click', () => {
    open = !open;
    drawer.classList.toggle('is-open', open);
    btn.setAttribute('aria-expanded', open);
    label.innerHTML = open
      ? 'Show fewer products <span class="arrow">&rarr;</span>'
      : 'View all products <span class="arrow">&rarr;</span>';
    if (open) {
      setTimeout(() => drawer.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 150);
    }
  });
})();
// Resources drawer — slide open to reveal remaining resource cards
(function () {
  const btn = document.getElementById('viewAllResourcesBtn');
  const label = document.getElementById('viewAllResourcesLabel');
  const drawer = document.getElementById('resourcesDrawer');
  if (!btn || !drawer) return;
  let open = false;
  btn.addEventListener('click', () => {
    open = !open;
    drawer.classList.toggle('is-open', open);
    btn.setAttribute('aria-expanded', open);
    label.innerHTML = open
      ? 'Show fewer resources <span class="arrow">&rarr;</span>'
      : 'View all resources <span class="arrow">&rarr;</span>';
    if (open) {
      setTimeout(() => drawer.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 150);
    }
  });
})();
// Mobile nav toggle
const navToggle = document.getElementById('navToggle');
const navLinks = document.getElementById('navLinks');
navToggle.addEventListener('click', () => {
  const isOpen = navLinks.classList.toggle('open');
  navToggle.setAttribute('aria-expanded', isOpen);
});
navLinks.querySelectorAll('a').forEach(link =>
  link.addEventListener('click', () => {
    navLinks.classList.remove('open');
    navToggle.setAttribute('aria-expanded', 'false');
  })
);

// Products/Resources/Updates dropdowns: hover handles desktop via CSS; this adds tap/keyboard support
const navDropdowns = document.querySelectorAll('.nav-item-dropdown');
navDropdowns.forEach(navDropdown => {
  const dropdownToggle = navDropdown.querySelector('.nav-dropdown-toggle');
  dropdownToggle.addEventListener('click', (e) => {
    if (window.matchMedia('(max-width:860px)').matches) {
      e.preventDefault();
      // close any other open dropdown first
      navDropdowns.forEach(other => {
        if (other !== navDropdown) {
          other.classList.remove('open');
          other.querySelector('.nav-dropdown-toggle').setAttribute('aria-expanded', 'false');
        }
      });
      const isOpen = navDropdown.classList.toggle('open');
      dropdownToggle.setAttribute('aria-expanded', isOpen);
    }
  });
});
document.addEventListener('click', (e) => {
  navDropdowns.forEach(navDropdown => {
    if (!navDropdown.contains(e.target)) {
      navDropdown.classList.remove('open');
      navDropdown.querySelector('.nav-dropdown-toggle').setAttribute('aria-expanded', 'false');
    }
  });
});

// Scroll reveal
const revealIO = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add('in'); revealIO.unobserve(e.target); }
  });
}, { threshold: 0.12 });
document.querySelectorAll('.reveal').forEach(el => revealIO.observe(el));

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Animated stat counters (About section)
const statEls = document.querySelectorAll('.stat .n[data-count], .trust-stat .n[data-count]');
if (statEls.length) {
  const animate = (el) => {
    const target = parseInt(el.getAttribute('data-count'), 10) || 0;
    const suffix = el.getAttribute('data-suffix') || '';
    if (prefersReducedMotion) { el.textContent = target + suffix; return; }
    const duration = 5000, start = performance.now();
    const step = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.round(target * eased) + suffix;
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  const statIO = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) { animate(e.target); statIO.unobserve(e.target); } });
  }, { threshold: 0.4 });
  statEls.forEach(el => statIO.observe(el));
}

// Founder quote carousel (tabs + prev/next)
(function () {
  const wrap = document.getElementById('founderQuotes');
  if (!wrap) return;
  const slides = [...wrap.querySelectorAll('.quote-slide')];
  const tabs = [...wrap.querySelectorAll('.quote-tab')];
  let current = 0;
  function show(i) {
    current = ((i % slides.length) + slides.length) % slides.length;
    slides.forEach((s, idx) => s.classList.toggle('is-active', idx === current));
    tabs.forEach((t, idx) => t.classList.toggle('is-active', idx === current));
  }
  window.founderQuoteNav = (dir) => show(current + dir);
  window.founderQuoteGoTo = (i) => show(i);
})();

// About slideshow (dots + autoplay)
(function () {
  const wrap = document.getElementById('aboutSlideshow');
  if (!wrap) return;
  const slides = [...wrap.querySelectorAll('.slideshow-track .slide')];
  const dotsWrap = document.getElementById('slideDots');
  let current = 0, timer;

  slides.forEach((_, i) => {
    const dot = document.createElement('span');
    dot.setAttribute('role', 'button');
    dot.setAttribute('aria-label', 'Go to slide ' + (i + 1));
    if (i === 0) dot.classList.add('is-active');
    dot.addEventListener('click', () => { show(i); restart(); });
    dotsWrap.appendChild(dot);
  });
  const dots = [...dotsWrap.children];

  function show(i) {
    slides[current].classList.remove('is-active');
    dots[current]?.classList.remove('is-active');
    current = ((i % slides.length) + slides.length) % slides.length;
    slides[current].classList.add('is-active');
    dots[current]?.classList.add('is-active');
  }
  function restart() {
    clearInterval(timer);
    timer = setInterval(() => show(current + 1), 4500);
  }

  window.aboutSlideshowNav = (dir) => { show(current + dir); restart(); };
  restart();
  wrap.addEventListener('mouseenter', () => clearInterval(timer));
  wrap.addEventListener('mouseleave', restart);
})();

// Header elevation + fade on scroll direction, reveal on hover near top
const headerEl = document.querySelector('header');
const headerHoverZone = document.getElementById('headerHoverZone');
let lastScrollY = window.scrollY;

const onScroll = () => {
  const y = window.scrollY;
  headerEl.classList.toggle('scrolled', y > 8);
  if (y <= 80) {
    headerEl.classList.remove('header-hidden');
  } else if (y > lastScrollY) {
    headerEl.classList.add('header-hidden');
  } else {
    headerEl.classList.remove('header-hidden');
  }
  lastScrollY = y;
};
onScroll();
window.addEventListener('scroll', onScroll, { passive: true });
headerHoverZone.addEventListener('mouseenter', () => headerEl.classList.remove('header-hidden'));

// Hero video zoom on scroll
const heroVideo = document.querySelector('.hero-bg video');
const heroSection = document.querySelector('.hero');
if (heroVideo && heroSection && !prefersReducedMotion) {
  const heroZoomOnScroll = () => {
    const rect = heroSection.getBoundingClientRect();
    const progress = Math.min(Math.max(1 - (rect.bottom / (rect.height + window.innerHeight)), 0), 1);
    heroVideo.style.transform = `scale(${1 + progress * 0.22})`;
  };
  heroZoomOnScroll();
  window.addEventListener('scroll', heroZoomOnScroll, { passive: true });
}

// Active nav-link tracking by section in view
const navAnchors = [...navLinks.querySelectorAll('a')];
const setActive = (id) => navAnchors.forEach(a =>
  a.classList.toggle('active', a.getAttribute('href') === '#' + id)
);
const sectionIO = new IntersectionObserver((entries) => {
  entries.forEach(e => { if (e.isIntersecting) setActive(e.target.id); });
}, { rootMargin: '-45% 0px -50% 0px', threshold: 0 });
['products', 'resources', 'track-record', 'about', 'contact']
  .map(id => document.getElementById(id))
  .filter(Boolean)
  .forEach(sec => sectionIO.observe(sec));
// Calculator modal open/close
(function () {
  const btn = document.getElementById('calculatorWidgetBtn');
  const overlay = document.getElementById('calculatorOverlay');
  const closeBtn = document.getElementById('calculatorModalClose');
  if (!btn || !overlay || !closeBtn) return;

  const openModal = () => {
    overlay.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  };
  const closeModal = () => {
    overlay.classList.remove('is-open');
    document.body.style.overflow = '';
  };

  btn.addEventListener('click', (e) => {
    e.preventDefault();
    openModal();
  });
  closeBtn.addEventListener('click', closeModal);
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && overlay.classList.contains('is-open')) closeModal();
  });
})();
// Pipe / Metal Weight Calculator logic
(function () {
  const shapeSelect   = document.getElementById('calcShape');
  const label1        = document.getElementById('calcLabel1');
  const label2        = document.getElementById('calcLabel2');
  const label3        = document.getElementById('calcLabel3');
  const field2Row      = document.getElementById('calcField2Row');
  const param1         = document.getElementById('calcParam1');
  const param2         = document.getElementById('calcParam2');
  const param3         = document.getElementById('calcParam3');
  const qtyInput       = document.getElementById('calcQty');
  const materialSelect = document.getElementById('calcMaterial');
  const calcBtn        = document.getElementById('calcCalculateBtn');
  const clearBtn       = document.getElementById('calcClearBtn');
  const errorBox       = document.getElementById('calcError');
  const resultsBox     = document.getElementById('calcResults');
  const resultLbs      = document.getElementById('calcResultLbs');
  const resultKg       = document.getElementById('calcResultKg');
  const historyBox        = document.getElementById('calcHistory');
  const historyList        = document.getElementById('calcHistoryList');
  const historyClearBtn    = document.getElementById('calcHistoryClearBtn');
  const historyConfirm     = document.getElementById('calcHistoryConfirm');
  const historyConfirmYes  = document.getElementById('calcHistoryConfirmYes');
  const historyConfirmNo   = document.getElementById('calcHistoryConfirmNo');
  const totalLbsEl         = document.getElementById('calcHistoryTotalLbs');
  const totalKgEl          = document.getElementById('calcHistoryTotalKg');

  let calcHistory = JSON.parse(localStorage.getItem('calcHistory') || '[]');

  if (!shapeSelect) return; // calculator not on this page

  const LABELS = {
    Round:      { l1: 'Diameter',        l2: null,               l3: 'Length' },
    Square:     { l1: 'Width',           l2: null,               l3: 'Length' },
    Hexagonal:  { l1: 'Diameter',        l2: null,               l3: 'Length' },
    Octagonal:  { l1: 'Diameter',        l2: null,               l3: 'Length' },
    Sheet:      { l1: 'Thickness',       l2: 'Width',            l3: 'Length' },
    Plate:      { l1: 'Thickness',       l2: 'Width',            l3: 'Length' },
    Rectangle:  { l1: 'Thickness',       l2: 'Width',            l3: 'Length' },
    Tubular:    { l1: 'Outer Diameter',  l2: 'Wall Thickness',   l3: 'Length' },
    Pipe:       { l1: 'Outer Diameter',  l2: 'Wall Thickness',   l3: 'Length' },
    Ring:       { l1: 'Outer Diameter',  l2: 'Inner Diameter',   l3: 'Thickness' }
  };

  function updateLabels() {
    const shape = shapeSelect.value;
    const cfg = LABELS[shape];
    label1.textContent = cfg.l1;
    label3.textContent = cfg.l3;
    if (cfg.l2) {
      label2.textContent = cfg.l2;
      field2Row.style.display = '';
    } else {
      field2Row.style.display = 'none';
      param2.value = '';
    }
  }
  shapeSelect.addEventListener('change', updateLabels);
  updateLabels();

  const shapeNameEl = document.getElementById('calcShapeName');
  const shapeIcons  = [...document.querySelectorAll('.calc-shape-icon')];
  const buzz = () => { if (navigator.vibrate) navigator.vibrate(12); };

  function selectShapeIcon(btn, { silent = false } = {}) {
    shapeSelect.value = btn.dataset.shape;
    shapeIcons.forEach(b => {
      b.classList.remove('is-active');
      b.setAttribute('aria-pressed', 'false');
    });
    btn.classList.add('is-active');
    btn.setAttribute('aria-pressed', 'true');
    if (shapeNameEl) shapeNameEl.textContent = btn.getAttribute('aria-label') || btn.dataset.shape;
    updateLabels();
    if (!silent) buzz();
  }

  shapeIcons.forEach(btn => {
    // Tactile press feedback (mirrors the header nav "pressed" behaviour)
    btn.addEventListener('touchstart', () => btn.classList.add('pressed'), { passive: true });
    btn.addEventListener('touchend',   () => btn.classList.remove('pressed'));
    btn.addEventListener('touchcancel',() => btn.classList.remove('pressed'));
    btn.addEventListener('mousedown',  () => btn.classList.add('pressed'));
    btn.addEventListener('mouseup',    () => btn.classList.remove('pressed'));
    btn.addEventListener('mouseleave', () => btn.classList.remove('pressed'));

    btn.addEventListener('click', () => selectShapeIcon(btn));
  });

  // macOS-dock-style magnify: the hovered icon grows and lifts most,
  // with immediate neighbours scaling up less, fading out by two positions.
  const dockReset = () => {
    shapeIcons.forEach(el => { el.style.transform = ''; });
  };
  const dockMagnify = (centerIndex) => {
    dockReset();
    const falloff = [
      { offset: -2, scale: 1.05, lift: 0   },
      { offset: -1, scale: 1.15, lift: -5  },
      { offset:  0, scale: 1.32, lift: -10 },
      { offset:  1, scale: 1.15, lift: -5  },
      { offset:  2, scale: 1.05, lift: 0   },
    ];
    falloff.forEach(({ offset, scale, lift }) => {
      const el = shapeIcons[centerIndex + offset];
      if (el) el.style.transform = `translateY(${lift}px) scale(${scale})`;
    });
  };
  shapeIcons.forEach((btn, index) => {
    btn.addEventListener('mouseenter', () => dockMagnify(index));
  });
  const shapeIconsBar = document.getElementById('calcShapeIcons');
  if (shapeIconsBar) shapeIconsBar.addEventListener('mouseleave', dockReset);

  // Keep the on-screen caption correct if the shape ever changes some other way
  if (shapeNameEl) {
    const activeBtn = shapeIcons.find(b => b.classList.contains('is-active')) || shapeIcons[0];
    if (activeBtn) shapeNameEl.textContent = activeBtn.getAttribute('aria-label') || activeBtn.dataset.shape;
  }

  function toInches(value, unit) {
    switch (unit) {
      case 'cm': return value / 2.54;
      case 'm':  return (value * 100) / 2.54;
      case 'mm': return (value / 10) / 2.54;
      case 'ft': return value * 12;
      case 'yd': return value * 36;
      default:   return value; // in
    }
  }

  function toFeet(value, unit) {
    switch (unit) {
      case 'cm': return (value / 2.54) / 12;
      case 'm':  return ((value * 100) / 2.54) / 12;
      case 'mm': return ((value / 10) / 2.54) / 12;
      case 'in': return value / 12;
      case 'yd': return value * 3;
      default:   return value; // ft
    }
  }

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.style.display = 'block';
    resultsBox.style.display = 'none';
  }

  function clearError() {
    errorBox.style.display = 'none';
  }

  function calculate() {
    clearError();
    const shape = shapeSelect.value;
    const cfg = LABELS[shape];

    const p1 = parseFloat(param1.value);
    const p2 = cfg.l2 ? parseFloat(param2.value) : 0;
    const p3 = parseFloat(param3.value);
    const qty = parseFloat(qtyInput.value) || 1;

    if (isNaN(p1) || isNaN(p3) || (cfg.l2 && isNaN(p2))) {
      showError('Please fill in all required dimension fields.');
      return;
    }

    const unit1 = document.getElementById('calcUnit1').value;
    const unit2 = document.getElementById('calcUnit2').value;
    const unit3 = document.getElementById('calcUnit3').value;

    const convert = parseFloat(materialSelect.options[materialSelect.selectedIndex].dataset.factor) || 1;

    let d1 = toInches(p1, unit1);
    let d2 = cfg.l2 ? toInches(p2, unit2) : 0;
    let lengthFt = toFeet(p3, unit3);
    let weight;

    switch (shape) {
      case 'Round':
        weight = 2.6729 * d1 * d1 * convert * lengthFt * qty;
        break;
      case 'Square':
        weight = 3.4032 * d1 * d1 * convert * lengthFt * qty;
        break;
      case 'Hexagonal':
        weight = 2.9473 * d1 * d1 * convert * lengthFt * qty;
        break;
      case 'Octagonal':
        weight = 2.8193 * d1 * d1 * convert * lengthFt * qty;
        break;
      case 'Sheet':
      case 'Plate':
      case 'Rectangle':
        weight = 3.4032 * d1 * convert * d2 * lengthFt * qty;
        break;
      case 'Tubular':
      case 'Pipe':
        weight = 10.68 * (d1 - d2) * convert * d2 * lengthFt * qty;
        if (weight < 0) {
          showError('Wall thickness cannot exceed the Outer Diameter.');
          return;
        }
        break;
      case 'Ring': {
        const thicknessIn = toInches(p3, unit3); // Ring's 3rd field is Thickness, used directly in inches
        weight = 0.22274 * thicknessIn * (d1 * d1 - d2 * d2) * convert * qty;
        if (weight < 0) {
          showError('Inner Diameter cannot exceed the Outer Diameter.');
          return;
        }
        break;
      }
    }

    const lbs = weight;
    const kg = weight * 0.453592;

    resultLbs.textContent = lbs.toFixed(2);
    resultKg.textContent = kg.toFixed(2);
    resultsBox.style.display = 'flex';
    const shortDesc = cfg.l2
      ? `${shape} · ${p1}${unit1}×${p2}${unit2}×${p3}${unit3} · Qty ${qty}`
      : `${shape} · ${p1}${unit1} × ${p3}${unit3} · Qty ${qty}`;
    addToHistory(shortDesc, lbs, kg);
  }

  function clearForm() {
    param1.value = '';
    param2.value = '';
    param3.value = '';
    qtyInput.value = '1';
    resultsBox.style.display = 'none';
    clearError();
  }
function saveHistory() {
    localStorage.setItem('calcHistory', JSON.stringify(calcHistory));
  }

  function renderHistory() {
    if (!calcHistory.length) {
      historyBox.style.display = 'none';
      return;
    }
    historyBox.style.display = 'flex';
    historyList.innerHTML = calcHistory.map(item => `
  <div class="calc-history-row" data-id="${item.id}">
    <span class="calc-history-desc">${item.desc}</span>
    <span class="calc-history-weight">${item.kg.toFixed(2)} kg</span>
    <button type="button" class="calc-history-remove" data-remove-id="${item.id}" aria-label="Remove">&times;</button>
  </div>
`).join('');

historyList.querySelectorAll('.calc-history-remove').forEach(btn => {
  btn.onclick = () => {
    const id = btn.dataset.removeId;
    calcHistory = calcHistory.filter(i => String(i.id) !== id);
    saveHistory();
    renderHistory();
  };
});

    const totalLbs = calcHistory.reduce((s, i) => s + i.lbs, 0);
    const totalKg  = calcHistory.reduce((s, i) => s + i.kg, 0);
    totalLbsEl.textContent = totalLbs.toFixed(2);
    totalKgEl.textContent  = totalKg.toFixed(2);
  }

  function addToHistory(desc, lbs, kg) {
    calcHistory.push({ id: Date.now() + Math.random(), desc, lbs, kg });
    saveHistory();
    renderHistory();
  }

  historyClearBtn.addEventListener('click', () => {
    historyConfirm.style.display = 'flex';
  });
  historyConfirmNo.addEventListener('click', () => {
    historyConfirm.style.display = 'none';
  });
 historyConfirmYes.addEventListener('click', () => {
    calcHistory = [];
    saveHistory();
    renderHistory();
    historyConfirm.style.display = 'none';
  });

const pdfBtn = document.getElementById('calcHistoryPdfBtn');

  // Fixed company details — no settings panel, no gear button.
  // Logo path is set here manually (point this at your logo file).
  const COMPANY_INFO = {
    name: 'MURTAZA CORPORATION',
    phone: '+92 (21) 35141451',
    email: 'sales@murtazacorporation.com.pk',
    location: '516/517, Sector 6-A, Mehran Town, Korangi Industrial Area, Karachi - 74900, Pakistan',
    logoPath: 'Logos/company.png'
  };

  // Loads the logo image from disk and converts it to a data URL jsPDF can embed.
  function loadLogoAsDataURL(path) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        canvas.getContext('2d').drawImage(img, 0, 0);
        try {
          resolve(canvas.toDataURL('image/png'));
        } catch (e) {
          resolve(null);
        }
      };
      img.onerror = () => resolve(null);
      img.src = path;
    });
  }

  async function exportHistoryToPDF() {
    if (!calcHistory.length) return;

    const { jsPDF } = window.jspdf;
    const doc = new jsPDF();
    const pageWidth  = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();

    // ---- Logo, fixed at the top-left every time ----
    const logoData = await loadLogoAsDataURL(COMPANY_INFO.logoPath);
    if (logoData) {
      doc.addImage(logoData, 'PNG', 20, 15, 32, 16);
    }

    doc.setFontSize(16);
    doc.setFont(undefined, 'bold');
    doc.setTextColor(30, 58, 168);
    doc.text('Weight Calculation', pageWidth / 2, 22, { align: 'center' });
    doc.setTextColor(0, 0, 0);

    // ---- Items table ----
    const rows = calcHistory.map(item => [
      item.desc,
      item.lbs.toFixed(2) + ' lbs',
      item.kg.toFixed(2) + ' kg'
    ]);

    const totalLbs = calcHistory.reduce((s, i) => s + i.lbs, 0);
    const totalKg  = calcHistory.reduce((s, i) => s + i.kg, 0);

    doc.autoTable({
      startY: 42,
      head: [['Item', 'Weight (lbs)', 'Weight (kg)']],
      body: rows,
      foot: [['Total', totalLbs.toFixed(2) + ' lbs', totalKg.toFixed(2) + ' kg']],
      theme: 'grid',
      headStyles: { fillColor: [30, 58, 168] },
      footStyles: { fillColor: [244, 246, 251], textColor: [30, 58, 168], fontStyle: 'bold' }
    });

    // ---- Footer, fixed near the bottom of the page ----
    // Company name is centered; location and contact details are right-aligned.
    const footerY = pageHeight - 25;
    const rightEdge = pageWidth - 20;

    doc.setDrawColor(220, 220, 220);
    doc.line(20, footerY - 6, rightEdge, footerY - 6);

    doc.setFontSize(10);
    doc.setFont(undefined, 'bold');
    doc.setTextColor(30, 58, 168);
    doc.text(COMPANY_INFO.name, pageWidth / 2, footerY, { align: 'center' });

    doc.setFontSize(8.5);
    doc.setFont(undefined, 'normal');
    doc.setTextColor(90, 90, 90);
   doc.text(COMPANY_INFO.location, rightEdge, footerY + 5, { align: 'right' });
    doc.text(`${COMPANY_INFO.email}   |   ${COMPANY_INFO.phone}`, rightEdge, footerY + 10, { align: 'right' });
    doc.setTextColor(0, 0, 0);

    // Standards verification note, bottom-right corner
    doc.setFontSize(7);
    doc.setFont(undefined, 'italic');
    doc.setTextColor(140, 140, 140);
    doc.text('Weights calculated per standard imperial steel weight formulas.', rightEdge, pageHeight - 10, { align: 'right' });
    doc.setTextColor(0, 0, 0);

    doc.save('weight-calculation.pdf');
  }

  pdfBtn.addEventListener('click', exportHistoryToPDF);
  renderHistory();
  calcBtn.addEventListener('click', calculate);
  clearBtn.addEventListener('click', clearForm);
})();
