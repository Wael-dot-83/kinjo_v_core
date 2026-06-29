// Simple Odometer (Count-Up) Animation for CYBERLUME standard
document.addEventListener("DOMContentLoaded", function() {
    const animateNumbers = () => {
        const numbers = document.querySelectorAll('.odometer, .cyberlume-number');
        
        numbers.forEach(el => {
            if (el.hasAttribute('data-animated')) return;
            
            // Try to parse the target number. Handle commas and decimals.
            const text = el.innerText.trim();
            // Don't animate if it's not a clear number or has complex formatting we don't want to break right now.
            const match = text.match(/^([\d,.]+)(.*)$/);
            
            if (match) {
                const numStr = match[1].replace(/,/g, '');
                const target = parseFloat(numStr);
                const suffix = match[2] || '';
                
                if (!isNaN(target)) {
                    el.setAttribute('data-animated', 'true');
                    let start = 0;
                    const duration = 1500; // 1.5 seconds
                    const frameDuration = 1000 / 60;
                    const totalFrames = Math.round(duration / frameDuration);
                    let frame = 0;
                    
                    const formatNumber = (num) => {
                        if (Number.isInteger(target)) {
                            return Math.round(num).toLocaleString('en-US') + suffix;
                        } else {
                            return num.toFixed(1) + suffix; // assume 1 decimal place for rates
                        }
                    };

                    const counter = setInterval(() => {
                        frame++;
                        const progress = frame / totalFrames;
                        // easeOutQuart
                        const ease = 1 - Math.pow(1 - progress, 4);
                        const current = start + (target - start) * ease;
                        
                        el.innerText = formatNumber(current);
                        
                        if (frame >= totalFrames) {
                            clearInterval(counter);
                            el.innerText = formatNumber(target);
                        }
                    }, frameDuration);
                }
            }
        });
    };

    // Run on load
    animateNumbers();
    
    // Create an observer to run it again when new content is loaded via fetch (e.g. dashboard updates)
    const observer = new MutationObserver((mutations) => {
        let shouldRun = false;
        mutations.forEach(m => {
            if (m.addedNodes.length > 0) shouldRun = true;
        });
        if (shouldRun) {
            setTimeout(animateNumbers, 100);
        }
    });
    
    const dashboardMain = document.getElementById('analyticsDashboardMain');
    if (dashboardMain) {
        observer.observe(dashboardMain, { childList: true, subtree: true });
    } else {
        observer.observe(document.body, { childList: true, subtree: true });
    }
});
