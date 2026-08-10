function showCartSuccess(message) {
    const existingMessage = document.querySelector(".cart-success-toast");
    if (existingMessage) existingMessage.remove();

    const notification = document.createElement("div");
    notification.className = "flash flash-success cart-success-toast";
    notification.setAttribute("role", "status");
    notification.setAttribute("aria-live", "polite");
    notification.textContent = message;
    document.body.appendChild(notification);

    requestAnimationFrame(() => notification.classList.add("cart-success-toast-visible"));
    setTimeout(() => {
        notification.classList.remove("cart-success-toast-visible");
        setTimeout(() => notification.remove(), 250);
    }, 2500);
}

document.addEventListener("click", async (event) => {
    const button = event.target.closest(".add-cart-button");
    if (!button) return;
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "Adding...";
    try {
        const response = await fetch(button.dataset.url, {
            method: "POST",
            headers: {"X-Requested-With": "XMLHttpRequest"}
        });
        const result = await response.json();
        if (response.status === 401) {
            window.location.href = "/user-login";
            return;
        }
        if (!response.ok || !result.success) throw new Error(result.message || "Could not add product.");
        const count = document.getElementById("cart-count");
        if (count) count.textContent = result.cart_count;
        showCartSuccess("Item added to cart.");
        button.textContent = "Added!";
        setTimeout(() => { button.textContent = originalText; }, 1200);
    } catch (error) {
        button.textContent = error.message;
        setTimeout(() => { button.textContent = originalText; }, 2000);
    } finally {
        button.disabled = false;
    }
});

const cartItemCheckboxes = document.querySelectorAll(".cart-item-checkbox");

function updateSelectedCartSummary() {
    let selectedCount = 0;
    let selectedTotal = 0;

    document.querySelectorAll("[data-cart-item]").forEach((item) => {
        const checkbox = item.querySelector(".cart-item-checkbox");
        const isSelected = checkbox && checkbox.checked;
        item.classList.toggle("cart-item-unselected", !isSelected);
        if (isSelected) {
            selectedCount += Number(item.dataset.quantity || 0);
            selectedTotal += Number(item.dataset.total || 0);
        }
    });

    const formattedTotal = `₹${selectedTotal.toFixed(2)}`;
    const count = document.getElementById("selected-cart-count");
    const subtotal = document.getElementById("selected-subtotal");
    const total = document.getElementById("selected-total");
    if (count) count.textContent = selectedCount;
    if (subtotal) subtotal.textContent = formattedTotal;
    if (total) total.textContent = formattedTotal;
}

cartItemCheckboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", updateSelectedCartSummary);
});
