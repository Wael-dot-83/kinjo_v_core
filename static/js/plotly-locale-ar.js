window.Plotly = window.Plotly || {};
window.PlotlyConfig = window.PlotlyConfig || {};
(function(){
  if (!window.Plotly || !window.Plotly.register) return;
  var locale = {
    moduleType: "locale",
    name: "ar",
    dictionary: {},
    format: {
      days: ["الأحد","الاثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت"],
      shortDays: ["أحد","اثنين","ثلاثاء","أربعاء","خميس","جمعة","سبت"],
      months: ["يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"],
      shortMonths: ["ينا","فبر","مار","أبر","ماي","يون","يول","أغس","سبت","أكت","نوف","ديس"],
      date: "%d/%m/%Y"
    }
  };
  window.Plotly.register(locale);
})();
