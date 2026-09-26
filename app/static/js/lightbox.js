/* Lightbox + delegated delete buttons (runs after page inits). */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function wireLightboxAndDeletes(reloaders) {
    document.addEventListener('click', async (event) => {
      const lightboxTarget = event.target.closest('[data-lightbox]');
      if (lightboxTarget && $('#lightbox')) {
        $('#lightbox-img').src = lightboxTarget.dataset.lightbox;
        $('#lightbox').classList.replace('hidden', 'flex');
        return;
      }
      const actions = [
        ['[data-delete-post]', 'deletePost', '/api/posts/', 'Delete this entry and its photos?', reloaders.posts],
        ['[data-delete-fert]', 'deleteFert', '/api/fertilizations/', 'Delete this fertilization entry?', reloaders.ferts],
        ['[data-delete-obs]', 'deleteObs', '/api/observations/', 'Delete this observation and its photos?', reloaders.obs],
      ];
      for (const [selector, key, endpoint, question, reload] of actions) {
        const button = event.target.closest(selector);
        if (button && window.confirm(question)) {
          try {
            await api.del(`${endpoint}${button.dataset[key]}`);
            toast('Entry deleted', 'ok');
            await reload?.();
          } catch (error) { toast(error.message, 'err'); }
          return;
        }
      }
    });
    const lightbox = $('#lightbox');
    if (lightbox) lightbox.addEventListener('click', () => lightbox.classList.replace('flex', 'hidden'));
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && lightbox) lightbox.classList.replace('flex', 'hidden');
    });
  }

  globalThis.Verdant.onBootLate((reloaders) => wireLightboxAndDeletes(reloaders));
})();
