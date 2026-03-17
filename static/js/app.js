/**
 * ALCOEN ERP Application JavaScript
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Auto-hide alerts after 5 seconds
    setTimeout(function() {
        var alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(function(alert) {
            var bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
    
    // Confirm delete actions
    document.querySelectorAll('form[onsubmit*="confirm"]').forEach(function(form) {
        form.addEventListener('submit', function(e) {
            if (!confirm('确定要执行此操作吗？')) {
                e.preventDefault();
            }
        });
    });
});

/**
 * Calculate total price dynamically
 */
function calculateTotal() {
    const quantityInput = document.getElementById('quantity');
    const priceInput = document.getElementById('price_with_tax');
    
    if (quantityInput && priceInput) {
        const quantity = parseFloat(quantityInput.value) || 0;
        const price = parseFloat(priceInput.value) || 0;
        const total = quantity * price;
        
        // Update any total display if exists
        const totalDisplay = document.getElementById('total_display');
        if (totalDisplay) {
            totalDisplay.textContent = total.toFixed(2);
        }
    }
}

/**
 * Format number as currency
 */
function formatCurrency(amount) {
    return new Intl.NumberFormat('zh-CN', {
        style: 'decimal',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(amount);
}

/**
 * Date utilities
 */
const DateUtils = {
    /**
     * Format date to YYYY-MM-DD
     */
    formatDate: function(date) {
        const d = new Date(date);
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    },
    
    /**
     * Get first day of current month
     */
    getFirstDayOfMonth: function() {
        const now = new Date();
        return this.formatDate(new Date(now.getFullYear(), now.getMonth(), 1));
    },
    
    /**
     * Get last day of current month
     */
    getLastDayOfMonth: function() {
        const now = new Date();
        return this.formatDate(new Date(now.getFullYear(), now.getMonth() + 1, 0));
    },
    
    /**
     * Get today's date
     */
    getToday: function() {
        return this.formatDate(new Date());
    }
};

/**
 * Form utilities
 */
const FormUtils = {
    /**
     * Serialize form data to object
     */
    serialize: function(form) {
        const formData = new FormData(form);
        const data = {};
        for (let [key, value] of formData.entries()) {
            data[key] = value;
        }
        return data;
    },
    
    /**
     * Clear form validation errors
     */
    clearErrors: function(form) {
        form.querySelectorAll('.is-invalid').forEach(function(el) {
            el.classList.remove('is-invalid');
        });
        form.querySelectorAll('.invalid-feedback').forEach(function(el) {
            el.remove();
        });
    }
};

/**
 * AJAX utilities
 */
const AjaxUtils = {
    /**
     * Get JSON data from URL
     */
    get: function(url, callback) {
        fetch(url, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => callback(null, data))
        .catch(error => callback(error, null));
    },
    
    /**
     * Post JSON data
     */
    post: function(url, data, callback) {
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(data => callback(null, data))
        .catch(error => callback(error, null));
    }
};
