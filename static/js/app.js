// Step celebration animation
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.step.done .step-number').forEach(function(el) {
    el.classList.add('celebrate');
  });
});
