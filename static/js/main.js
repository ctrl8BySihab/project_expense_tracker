// main.js — students will add JavaScript here as features are built

document.querySelectorAll('.password-toggle').forEach(function (btn) {
    btn.addEventListener('click', function () {
        var input = document.getElementById(btn.dataset.target);
        var isHidden = input.type === 'password';
        input.type = isHidden ? 'text' : 'password';
        btn.textContent = isHidden ? 'Hide' : 'Show';
        btn.setAttribute('aria-label', isHidden ? 'Hide password' : 'Show password');
    });
});
