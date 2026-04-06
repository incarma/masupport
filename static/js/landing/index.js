/* django_ma/static/js/landing/index.js */

(function () {
  'use strict';

  function getById(id) {
    return document.getElementById(id);
  }

  function addVisibleLater(el, delaySeconds) {
    if (!el) return;
    setTimeout(function () {
      el.classList.add('is-visible');
    }, delaySeconds * 1000);
  }

  function initObjectAnimations() {
    var obj = getById('objTitleCounselor');
    var tagline = getById('heroTagline');

    if (!obj) return;

    var delay = parseFloat(obj.dataset.delay || '0.3');

    requestAnimationFrame(function () {
      addVisibleLater(obj, delay);

      if (tagline) {
        addVisibleLater(tagline, delay + 0.4);
      }
    });
  }

  function initLoginModal() {
    var btnOpen = getById('btnOpenLogin');
    var btnClose = getById('btnCloseLogin');
    var modal = getById('loginModal');
    var backdrop = getById('modalBackdrop');
    var loginForm = getById('loginForm');
    var loginError = getById('loginError');
    var inputEmpId = getById('inputEmpId');
    var inputPassword = getById('inputPassword');
    var btnSubmit = getById('btnSubmitLogin');

    if (!btnOpen || !btnClose || !modal || !backdrop || !loginForm || !loginError || !btnSubmit) {
      return;
    }

    var isOpen = false;

    function showError(message) {
      loginError.textContent = message || '오류가 발생했습니다.';
      loginError.classList.add('is-visible');
    }

    function clearError() {
      loginError.textContent = '';
      loginError.classList.remove('is-visible');
    }

    function openModal() {
      if (isOpen) return;

      isOpen = true;
      modal.classList.add('is-open');
      backdrop.classList.add('is-open');
      backdrop.setAttribute('aria-hidden', 'false');
      btnOpen.setAttribute('aria-expanded', 'true');
      document.body.style.overflow = 'hidden';

      setTimeout(function () {
        if (inputEmpId) {
          inputEmpId.focus();
        }
      }, 100);
    }

    function closeModal() {
      if (!isOpen) return;

      isOpen = false;
      modal.classList.remove('is-open');
      backdrop.classList.remove('is-open');
      backdrop.setAttribute('aria-hidden', 'true');
      btnOpen.setAttribute('aria-expanded', 'false');
      document.body.style.overflow = '';
      clearError();
      btnOpen.focus();
    }

    function getCsrfToken() {
      var cookie = document.cookie
        .split('; ')
        .find(function (row) {
          return row.indexOf('csrftoken=') === 0;
        });

      return cookie ? cookie.split('=')[1] : '';
    }

    btnOpen.addEventListener('click', openModal);
    btnClose.addEventListener('click', closeModal);
    backdrop.addEventListener('click', closeModal);

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && isOpen) {
        closeModal();
      }
    });

    modal.addEventListener('keydown', function (event) {
      if (event.key !== 'Tab') return;

      var focusable = Array.from(
        modal.querySelectorAll(
          'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      );

      if (!focusable.length) return;

      var first = focusable[0];
      var last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    loginForm.addEventListener('submit', function (event) {
      event.preventDefault();

      var empId = inputEmpId ? inputEmpId.value.trim() : '';
      var password = inputPassword ? inputPassword.value : '';

      if (!empId || !password) {
        showError('사번과 비밀번호를 모두 입력해 주세요.');
        return;
      }

      if (btnSubmit.dataset.submitting === '1') {
        return;
      }

      btnSubmit.dataset.submitting = '1';
      btnSubmit.disabled = true;
      btnSubmit.textContent = '확인 중...';
      clearError();

      fetch('/login/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': getCsrfToken(),
          'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        body: new URLSearchParams({
          username: empId,
          password: password
        })
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (data) {
          if (data && data.success) {
            window.location.href = data.next_url || '/support/';
            return;
          }

          showError((data && data.message) || '로그인에 실패했습니다.');
        })
        .catch(function () {
          showError('네트워크 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
        })
        .finally(function () {
          btnSubmit.disabled = false;
          btnSubmit.textContent = '로그인';
          delete btnSubmit.dataset.submitting;
        });
    });
  }

  function initNavScroll() {
    var nav = getById('landingNav');
    if (!nav) return;

    var ticking = false;

    window.addEventListener(
      'scroll',
      function () {
        if (ticking) return;

        requestAnimationFrame(function () {
          nav.classList[window.scrollY > 20 ? 'add' : 'remove']('scrolled');
          ticking = false;
        });

        ticking = true;
      },
      { passive: true }
    );
  }

  function createObserver(targets) {
    if (!targets.length || typeof IntersectionObserver === 'undefined') {
      targets.forEach(function (el) {
        el.classList.add('is-visible');
      });
      return;
    }

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;

          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        });
      },
      { threshold: 0.12 }
    );

    targets.forEach(function (el) {
      observer.observe(el);
    });
  }

  function initSection1Animations() {
    var targets = [
      getById('s1TitleImg'),
      getById('s1Cards'),
      getById('s1TimelineImg')
    ].filter(Boolean);

    createObserver(targets);
  }

  function initSection2Animations() {
    var targets = [
      getById('s2TitleImg'),
      getById('s2ContentsImg')
    ].filter(Boolean);

    createObserver(targets);
  }

  function initSection3Sequence() {
    var section = getById('section-3');
    var title = getById('s3TitleImg');
    var boxes = [
      getById('s3Box1'),
      getById('s3Box2'),
      getById('s3Box3')
    ].filter(Boolean);
    var note = getById('s3NoteImg');

    if (!section || !title || !boxes.length) {
      return;
    }

    function playSequence() {
      if (section.dataset.animated === '1') {
        return;
      }
      section.dataset.animated = '1';

      title.classList.add('is-visible');

      setTimeout(function () {
        boxes.forEach(function (box) {
          box.classList.add('is-visible');
        });
      }, 850);

      setTimeout(function () {
        if (note) {
          note.classList.add('is-visible');
        }
      }, 1500);
    }

    if (typeof IntersectionObserver === 'undefined') {
      playSequence();
      return;
    }

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        playSequence();
        observer.unobserve(entry.target);
      });
    }, {
      threshold: 0.28
    });

    observer.observe(section);
  }

  function initSection4Sequence() {
    var section = getById('section-4');
    var title = getById('s4TitleImg');
    var boxes = [
      getById('s4Box1'),
      getById('s4Box2'),
      getById('s4Box3')
    ].filter(Boolean);

    if (!section || !title || !boxes.length) {
      return;
    }

    function playSequence() {
      if (section.dataset.animated === '1') {
        return;
      }
      section.dataset.animated = '1';

      title.classList.add('is-visible');

      setTimeout(function () {
        boxes.forEach(function (box) {
          box.classList.add('is-visible');
        });
      }, 650);
    }

    if (typeof IntersectionObserver === 'undefined') {
      playSequence();
      return;
    }

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        playSequence();
        observer.unobserve(entry.target);
      });
    }, {
      threshold: 0.28
    });

    observer.observe(section);
  }

  function bindScrollArrow(arrowId, targetId) {
    var arrow = getById(arrowId);
    var target = getById(targetId);

    if (!arrow || !target) return;

    function scrollToTarget(event) {
      event.preventDefault();
      target.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
    }

    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        arrow.classList.add('is-visible');
      });
    });

    arrow.addEventListener('click', scrollToTarget);
    arrow.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ' ') {
        scrollToTarget(event);
      }
    });
  }

  function init() {
    initObjectAnimations();
    initLoginModal();
    initNavScroll();
    initSection1Animations();
    initSection2Animations();
    initSection3Sequence();
    initSection4Sequence();
    bindScrollArrow('scrollDownArrow', 'section-1');
    bindScrollArrow('scrollDownArrow1', 'section-2');
    bindScrollArrow('scrollDownArrow2', 'section-3');
    bindScrollArrow('scrollDownArrow3', 'section-4');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();