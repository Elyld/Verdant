/* Full-screen slideshow page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  /* ------------------------------ Slideshow ------------------------------ */

  function initSlideshow() {
    const select = $('#fs-album');
    if (!select) return;
    const empty = $('#fs-empty');
    const figure = $('#fs-figure');
    const img = $('#fs-img');
    const title = $('#fs-title');
    const exif = $('#fs-exif');
    const counter = $('#fs-counter');
    const playBtn = $('#fs-play');
    const intervalSel = $('#fs-interval');
    let slides = [];
    let index = 0;
    let timer = null;

    function exifLine(slide) {
      const bits = [];
      if (slide.taken_at) bits.push(fmtDateTime(slide.taken_at));
      const cam = [slide.camera_make, slide.camera_model].filter(Boolean).join(' ').trim();
      if (cam) bits.push(cam);
      return bits.join(' · ');
    }

    function render() {
      if (!slides.length) {
        figure.classList.add('hidden');
        empty.classList.remove('hidden');
        empty.textContent = select.value ? 'This album has no photos yet.' : 'Pick an album above to begin.';
        return;
      }
      empty.classList.add('hidden');
      figure.classList.remove('hidden');
      const slide = slides[index];
      img.src = slide.file_path;
      img.alt = slide.title || slide.original_name || 'Garden photo';
      title.textContent = slide.title || slide.original_name || '';
      exif.textContent = exifLine(slide);
      counter.textContent = `${index + 1} / ${slides.length}`;
      [1, slides.length - 1].forEach((offset) => {
        const preload = new Image();
        preload.src = slides[(index + offset) % slides.length].file_path;
      });
    }

    function go(delta) {
      if (!slides.length) return;
      index = (index + delta + slides.length) % slides.length;
      render();
    }

    function play() {
      stop();
      timer = setInterval(() => go(1), Number(intervalSel.value) || 5000);
      playBtn.textContent = '⏸ Pause';
    }

    function stop() {
      if (timer) clearInterval(timer);
      timer = null;
      playBtn.textContent = '▶ Play';
    }

    async function openAlbum(id) {
      stop();
      if (!id) { slides = []; index = 0; render(); return; }
      try {
        const album = await api.get(`/api/albums/${id}`);
        slides = album.images || [];
        index = 0;
        render();
        if (slides.length) play();
      } catch (error) {
        toast(`Could not load album: ${error.message}`, 'err');
      }
    }

    async function loadAlbums() {
      const albums = await api.get('/api/albums');
      select.innerHTML = '<option value="">Choose an album…</option>'
        + albums.map((a) => `<option value="${a.id}">${esc(a.name)} (${(a.images || []).length})</option>`).join('');
      const params = new URLSearchParams(location.search);
      const preselect = params.get('album');
      if (preselect) { select.value = preselect; openAlbum(preselect); }
    }

    select.addEventListener('change', () => openAlbum(select.value));
    intervalSel.addEventListener('change', () => { if (timer && slides.length) play(); });
    $('#fs-prev').addEventListener('click', () => go(-1));
    $('#fs-next').addEventListener('click', () => go(1));
    playBtn.addEventListener('click', () => { if (timer) stop(); else if (slides.length) play(); });
    $('#fs-full').addEventListener('click', () => {
      const stage = $('#slide-stage');
      if (document.fullscreenElement) document.exitFullscreen();
      else if (stage.requestFullscreen) stage.requestFullscreen();
    });
    document.addEventListener('keydown', (event) => {
      if (!slides.length) return;
      if (event.key === 'ArrowLeft') go(-1);
      else if (event.key === 'ArrowRight') go(1);
      else if (event.key === ' ') { event.preventDefault(); if (timer) stop(); else play(); }
    });
    loadAlbums().catch((error) => toast(`Could not load albums: ${error.message}`, 'err'));
  }

  /* ------------------------------ Quick log ------------------------------ */

  globalThis.Verdant.onBoot(initSlideshow);
})();
