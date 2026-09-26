/* Photos page: local albums + slideshow. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function initPhotos() {
    const picker = $('#photo-album-select');
    if (!picker) return;
    const viewer = $('#slideshow');
    const empty = $('#photos-empty');
    const stage = $('#slide-stage');
    const img = $('#slide-img');
    const caption = $('#slide-caption');
    const counter = $('#slide-counter');
    const playBtn = $('#slide-play');
    let slides = [];
    let index = 0;
    let timer = null;

    async function loadAlbums(selectId) {
      const albums = await api.get('/api/albums');
      picker.innerHTML = '<option value="">Choose an album…</option>'
        + albums.map((a) => `<option value="${a.id}">${esc(a.name)} (${(a.images || []).length})</option>`).join('');
      if (selectId) picker.value = String(selectId);
    }

    function render() {
      if (!slides.length) {
        viewer.classList.add('hidden');
        empty.classList.remove('hidden');
        empty.textContent = picker.value ? 'This album has no photos yet.' : 'Choose an album above to start the slideshow.';
        return;
      }
      empty.classList.add('hidden');
      viewer.classList.remove('hidden');
      const slide = slides[index];
      img.src = slide.file_path;
      img.alt = slide.title || slide.original_name || 'Garden photo';
      caption.textContent = slide.title || slide.original_name || '';
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
      timer = setInterval(() => go(1), 5000);
      playBtn.innerHTML = '&#10074;&#10074; Pause';
    }

    function stop() {
      if (timer) clearInterval(timer);
      timer = null;
      playBtn.innerHTML = '&#9654; Play';
    }

    async function openAlbum(id) {
      stop();
      const dedicated = $('#slide-dedicated');
      if (dedicated) dedicated.href = id ? `/slideshow?album=${id}` : '/slideshow';
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

    picker.addEventListener('change', () => openAlbum(picker.value));
    $('#photo-refresh').addEventListener('click', () => loadAlbums().catch((error) => toast(`Could not load albums: ${error.message}`, 'err')));
    $('#slide-prev').addEventListener('click', () => go(-1));
    $('#slide-next').addEventListener('click', () => go(1));
    playBtn.addEventListener('click', () => { if (timer) stop(); else if (slides.length) play(); });
    $('#slide-fullscreen').addEventListener('click', () => {
      if (document.fullscreenElement) document.exitFullscreen();
      else if (stage.requestFullscreen) stage.requestFullscreen();
    });
    document.addEventListener('keydown', (event) => {
      if (!slides.length || viewer.classList.contains('hidden')) return;
      if (event.key === 'ArrowLeft') go(-1);
      else if (event.key === 'ArrowRight') go(1);
    });
    document.addEventListener('verdant:albums-changed', (event) => {
      loadAlbums(event.detail && event.detail.selectId)
        .then(() => openAlbum(picker.value))
        .catch((error) => toast(`Could not load albums: ${error.message}`, 'err'));
    });
    loadAlbums().catch((error) => toast(`Could not load albums: ${error.message}`, 'err'));
  }

  globalThis.Verdant.onBoot(initPhotos);
})();
