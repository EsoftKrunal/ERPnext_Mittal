// Copyright (c) 2026, Administrator and contributors
// For license information, please see license.txt

frappe.pages["purchase-analytics"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Purchase Tracking & Analytics"),
        single_column: true
    });
    
    // Create the container for custom HTML/CSS
    var main_container = $('<div class="purchase-analytics-dashboard"></div>').appendTo(page.main);
    
    // Define filters
    let def_company = frappe.defaults.get_default("company") || frappe.defaults.get_user_default("Company") || "";
    let company_filter = page.add_field({
        fieldname: "company",
        label: __("Company"),
        fieldtype: "Link",
        options: "Company",
        default: def_company,
        change: () => refresh_data()
    });
    
    let supplier_filter = page.add_field({
        fieldname: "supplier",
        label: __("Supplier"),
        fieldtype: "Link",
        options: "Supplier",
        change: () => refresh_data()
    });
    
    let item_filter = page.add_field({
        fieldname: "item_code",
        label: __("Item"),
        fieldtype: "Link",
        options: "Item",
        change: () => refresh_data()
    });
    
    let status_filter = page.add_field({
        fieldname: "status_filter",
        label: __("Filter Status"),
        fieldtype: "Select",
        options: ["All Open", "Pending Only", "Overdue Only"],
        default: "All Open",
        change: () => refresh_data()
    });
    
    let from_date_filter = page.add_field({
        fieldname: "from_date",
        label: __("From Expected Date"),
        fieldtype: "Date",
        change: () => refresh_data()
    });
    
    let to_date_filter = page.add_field({
        fieldname: "to_date",
        label: __("To Expected Date"),
        fieldtype: "Date",
        change: () => refresh_data()
    });
    
    // Add primary actions (Refresh, Export)
    page.set_primary_action(__("Refresh"), () => refresh_data(), "refresh");
    page.set_secondary_action(__("Export CSV"), () => export_to_csv(), "download");
    
    // Setup dashboard HTML structure
    main_container.html(`
        <div id="po-tracking-dashboard">
            <!-- KPI Cards Grid -->
            <div class="kpi-grid">
                <div class="kpi-card" id="kpi-open-pos">
                    <div class="kpi-icon"><i class="fa fa-shopping-cart text-primary"></i></div>
                    <div class="kpi-info">
                        <span class="kpi-label" id="kpi-open-pos-label">Open Purchase Orders</span>
                        <h3 class="kpi-val" id="val-open-pos">0</h3>
                    </div>
                </div>
                <div class="kpi-card" id="kpi-pending-qty">
                    <div class="kpi-icon"><i class="fa fa-cubes text-info"></i></div>
                    <div class="kpi-info">
                        <span class="kpi-label">Pending Quantity</span>
                        <h3 class="kpi-val" id="val-pending-qty">0</h3>
                    </div>
                </div>
                <div class="kpi-card" id="kpi-outstanding-val">
                    <div class="kpi-icon"><i class="fa fa-money text-success"></i></div>
                    <div class="kpi-info">
                        <span class="kpi-label" id="kpi-outstanding-val-label">Pending Value</span>
                        <h3 class="kpi-val" id="val-outstanding-val">0</h3>
                    </div>
                </div>
                <div class="kpi-card" id="kpi-pending-bill-val">
                    <div class="kpi-icon"><i class="fa fa-file-text-o text-warning"></i></div>
                    <div class="kpi-info">
                        <span class="kpi-label">Pending Bill Value</span>
                        <h3 class="kpi-val" id="val-pending-bill-val">0</h3>
                    </div>
                </div>
                <div class="kpi-card" id="kpi-overdue-pos">
                    <div class="kpi-icon"><i class="fa fa-exclamation-circle text-danger"></i></div>
                    <div class="kpi-info">
                        <span class="kpi-label">Overdue Items</span>
                        <h3 class="kpi-val" id="val-overdue-pos">0</h3>
                    </div>
                </div>
            </div>

            <!-- Charts Grid -->
            <div class="charts-grid">
                <div class="chart-card">
                    <div class="chart-header">
                        <span class="chart-title" id="chart-supplier-title">Pending Value by Supplier</span>
                    </div>
                    <div id="chart-supplier" class="chart-container"></div>
                </div>
                <div class="chart-card">
                    <div class="chart-header">
                        <span class="chart-title" id="chart-status-title">Overdue vs Pending Items</span>
                    </div>
                    <div id="chart-status" class="chart-container"></div>
                </div>
                <div class="chart-card">
                    <div class="chart-header">
                        <span class="chart-title" id="chart-ageing-title">PO Ageing (No. of POs)</span>
                    </div>
                    <div id="chart-ageing" class="chart-container"></div>
                </div>
                <div class="chart-card">
                    <div class="chart-header">
                        <span class="chart-title" id="chart-billing-title">Billing Status (by Value)</span>
                    </div>
                    <div id="chart-billing" class="chart-container"></div>
                </div>
            </div>
            
            <!-- Search & Info Panel -->
            <div class="panel-header" style="display: flex; justify-content: space-between; align-items: center; gap: 15px; flex-wrap: wrap;">
                <div class="search-box-wrapper" style="flex: 1; min-width: 250px;">
                    <input type="text" id="po-search-input" class="form-control po-search-input" placeholder="Search by PO No, Supplier, Item Code or Name..." />
                    <i class="fa fa-search search-icon"></i>
                </div>
                <div class="filter-badges-wrapper" style="display: flex; gap: 10px; align-items: center;">
                    <div id="results-count" class="results-count">Showing 0 items</div>
                    <div id="active-ageing-badge" class="badge badge-info" style="display: none; cursor: pointer; padding: 6px 12px; font-size: 11px; border-radius: 12px; background-color: #3182ce; color: white;">
                        <span id="active-ageing-text"></span> <i class="fa fa-times" style="margin-left: 5px;"></i>
                    </div>
                    <div id="active-billing-badge" class="badge badge-info" style="display: none; cursor: pointer; padding: 6px 12px; font-size: 11px; border-radius: 12px; background-color: #319795; color: white;">
                        <span id="active-billing-text"></span> <i class="fa fa-times" style="margin-left: 5px;"></i>
                    </div>
                </div>
            </div>
            
            <!-- Table Area -->
            <div class="table-container">
                <table class="po-table" id="po-table">
                    <thead>
                        <tr>
                            <th data-sort="po_no">PO Number <i class="fa fa-sort"></i></th>
                            <th data-sort="po_date">PO Date <i class="fa fa-sort"></i></th>
                            <th data-sort="ageing_days" class="text-right">Ageing (Days) <i class="fa fa-sort"></i></th>
                            <th data-sort="required_date">Expected Date <i class="fa fa-sort"></i></th>
                            <th data-sort="supplier">Supplier <i class="fa fa-sort"></i></th>
                            <th data-sort="item_code">Item Code <i class="fa fa-sort"></i></th>
                            <th data-sort="item_name">Item Name <i class="fa fa-sort"></i></th>
                            <th data-sort="ordered_qty" class="text-right">Ordered Qty <i class="fa fa-sort"></i></th>
                            <th data-sort="outstanding_qty" class="text-right">Pending Qty <i class="fa fa-sort"></i></th>
                            <th data-sort="billed_qty" class="text-right">Billed Qty <i class="fa fa-sort"></i></th>
                            <th data-sort="pending_billed_qty" class="text-right">Pending Bill Qty <i class="fa fa-sort"></i></th>
                            <th data-sort="pending_bill_val" class="text-right">Pending Bill Value <i class="fa fa-sort"></i></th>
                            <th data-sort="rate" class="text-right">Rate <i class="fa fa-sort"></i></th>
                            <th data-sort="amount" class="text-right">Amount <i class="fa fa-sort"></i></th>
                        </tr>
                    </thead>
                    <tbody id="po-table-body">
                        <tr>
                            <td colspan="14" class="text-center text-muted">Loading data...</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    `);

    // State Variables
    let report_data = [];
    let po_current_page = 1;
    let po_page_size = 20;
    let current_sort = { key: "required_date", asc: true };
    let current_ageing_filter = null;
    let current_billing_filter = null;
    let current_currency = "INR";

    const API = "custom_dashbords.api.purchase_analytics.get_po_data";

    function refresh_data() {
        current_ageing_filter = null;
        current_billing_filter = null;
        let filters = {
            company: company_filter ? company_filter.get_value() : null,
            supplier: supplier_filter ? supplier_filter.get_value() : null,
            item_code: item_filter ? item_filter.get_value() : null,
            status_filter: status_filter ? status_filter.get_value() : "All Open",
            from_date: from_date_filter ? from_date_filter.get_value() : null,
            to_date: to_date_filter ? to_date_filter.get_value() : null
        };
        
        frappe.call({
            method: API,
            args: filters,
            callback: function(r) {
                if (r.message) {
                    report_data = r.message.items || [];
                    current_currency = r.message.currency || "INR";
                    update_kpis(r.message.kpis || {}, current_currency, filters.status_filter);
                    sort_and_render();
                    render_charts(report_data, filters.status_filter);
                }
            }
        });
    }

    function update_kpis(kpis, currency, status) {
        $("#val-open-pos").text(kpis.total_open_pos || 0);
        $("#val-pending-qty").text(fmt_float(kpis.total_outstanding_qty || 0));
        $("#val-outstanding-val").html(format_currency_html(kpis.total_outstanding_val || 0, currency));
        $("#val-pending-bill-val").html(format_currency_html(kpis.total_pending_bill_val || 0, currency));
        $("#val-overdue-pos").text(kpis.overdue_count || 0);
        
        let label1 = __("Open Purchase Orders");
        let label3 = __("Pending Value");
        
        if (status === "Pending Only") {
            label1 = __("Pending Purchase Orders");
            label3 = __("Pending Value");
        } else if (status === "Overdue Only") {
            label1 = __("Overdue Purchase Orders");
            label3 = __("Overdue Value");
        }
        
        $("#kpi-open-pos-label").text(label1);
        $("#kpi-outstanding-val-label").text(label3);
        
        if ((kpis.overdue_count || 0) > 0) {
            $("#kpi-overdue-pos").addClass("kpi-danger-pulse");
        } else {
            $("#kpi-overdue-pos").removeClass("kpi-danger-pulse");
        }
    }

    let supplier_chart = null;
    let status_chart = null;

    function destroy_charts() {
        if (supplier_chart) { try { supplier_chart.destroy(); } catch(e) {} supplier_chart = null; }
        if (status_chart) { try { status_chart.destroy(); } catch(e) {} status_chart = null; }
        $("#chart-supplier").empty();
        $("#chart-status").empty();
        $("#chart-ageing").empty();
        $("#chart-billing").empty();
    }

    function render_charts(data, status) {
        destroy_charts();
        
        if (!data || data.length === 0) {
            $("#chart-supplier").html('<div style="text-align:center;color:#a0aec0;padding:60px;">No data</div>');
            $("#chart-status").html('<div style="text-align:center;color:#a0aec0;padding:60px;">No data</div>');
            $("#chart-ageing").html('<div style="text-align:center;color:#a0aec0;padding:60px;">No data</div>');
            $("#chart-billing").html('<div style="text-align:center;color:#a0aec0;padding:60px;">No data</div>');
            return;
        }

        // 1. Supplier Chart
        let supplier_sums = {};
        data.forEach(row => {
            supplier_sums[row.supplier] = (supplier_sums[row.supplier] || 0) + (row.outstanding_amount || 0);
        });
        
        let sorted_suppliers = Object.keys(supplier_sums)
            .map(supplier => ({ name: supplier, value: supplier_sums[supplier] }))
            .sort((a, b) => b.value - a.value);
            
        let top_suppliers = sorted_suppliers.slice(0, 5);
        let others_val = sorted_suppliers.slice(5).reduce((sum, item) => sum + item.value, 0);
        if (others_val > 0) top_suppliers.push({ name: __("Others"), value: others_val });
        
        let chart1_title = (status === "Overdue Only") ? __("Overdue Value by Supplier") : __("Pending Value by Supplier");
        $("#chart-supplier-title").text(chart1_title);
        
        let total_supp_val = top_suppliers.reduce((acc, s) => acc + s.value, 0);
        if (total_supp_val > 0) {
            supplier_chart = new frappe.Chart("#chart-supplier", {
                data: {
                    labels: top_suppliers.map(s => s.name),
                    datasets: [{ name: __("Pending Value"), values: top_suppliers.map(s => Math.round(s.value)) }]
                },
                type: "bar",
                height: 280,
                colors: ["#3182ce"],
                dataPointSelection: function(event) {
                    if (event && event.label && event.label !== __("Others")) {
                        supplier_filter.set_value(event.label);
                        refresh_data();
                    }
                }
            });
        } else {
            $("#chart-supplier").html('<div style="text-align:center;color:#a0aec0;padding:60px;">No data</div>');
        }
        
        // 2. Status Chart
        if (status === "All Open") {
            $("#chart-status-title").text(__("Overdue vs Pending Items"));
            let overdue_count = data.filter(row => row.is_overdue).length;
            let pending_count = data.length - overdue_count;
            let total = overdue_count + pending_count || 1;
            let overdue_pct = Math.round((overdue_count / total) * 100);
            let pending_pct = 100 - overdue_pct;

            $("#chart-status").html(`
                <div class="stat-ring-card">
                    <div class="stat-ring-item clickable" id="stat-overdue-click" style="cursor:pointer; flex: 1; text-align: right; padding-right: 20px;">
                        <div class="stat-split-label">Overdue</div>
                        <div class="stat-split-num" style="color:#e53e3e; font-size: 32px; font-weight: 700;">${overdue_count}</div>
                        <div class="stat-split-pct" style="color:#e53e3e; font-size: 11px; font-weight: 600; text-transform: uppercase;">${overdue_pct}% of total</div>
                    </div>
                    
                    <div class="stat-ring-wrapper">
                        <svg width="110" height="110" viewBox="0 0 120 120">
                            <circle cx="60" cy="60" r="50" fill="transparent" stroke="#e2e8f0" stroke-width="10"/>
                            <circle cx="60" cy="60" r="50" fill="transparent" stroke="#319795" stroke-width="10"/>
                            <circle cx="60" cy="60" r="50" fill="transparent" stroke="#e53e3e" stroke-width="10"
                                    stroke-dasharray="314" stroke-dashoffset="${314 - (314 * overdue_pct) / 100}"
                                    stroke-linecap="round" transform="rotate(-90 60 60)"/>
                        </svg>
                        <div class="stat-ring-center">
                            <span class="stat-ring-percent">${overdue_pct}%</span>
                            <span class="stat-ring-label">Overdue</span>
                        </div>
                    </div>
                    
                    <div class="stat-ring-item clickable" id="stat-pending-click" style="cursor:pointer; flex: 1; text-align: left; padding-left: 20px;">
                        <div class="stat-split-label">On Track</div>
                        <div class="stat-split-num" style="color:#319795; font-size: 32px; font-weight: 700;">${pending_count}</div>
                        <div class="stat-split-pct" style="color:#319795; font-size: 11px; font-weight: 600; text-transform: uppercase;">${pending_pct}% of total</div>
                    </div>
                </div>
                <div class="stat-split-total" style="margin-top: 10px;">Total: ${total} items</div>
            `);

            $("#stat-overdue-click").on("click", function() { status_filter.set_value("Overdue Only"); refresh_data(); });
            $("#stat-pending-click").on("click", function() { status_filter.set_value("Pending Only"); refresh_data(); });
        } else if (status === "Pending Only") {
            $("#chart-status-title").text(__("Expected Delivery Schedule (by Month)"));
            let month_sums = {};
            data.forEach(row => {
                let month = row.required_date ? row.required_date.substring(0, 7) : "Unknown";
                month_sums[month] = (month_sums[month] || 0) + (row.outstanding_amount || 0);
            });
            let sorted_months = Object.keys(month_sums).sort();
            status_chart = new frappe.Chart("#chart-status", {
                data: {
                    labels: sorted_months,
                    datasets: [{ name: __("Pending Value"), values: sorted_months.map(m => Math.round(month_sums[m])) }]
                },
                type: "bar", height: 280, colors: ["#319795"]
            });
        } else if (status === "Overdue Only") {
            $("#chart-status-title").text(__("Overdue Value by Item"));
            let item_sums = {};
            data.forEach(row => { item_sums[row.item_code] = (item_sums[row.item_code] || 0) + (row.outstanding_amount || 0); });
            let top_items = Object.keys(item_sums).map(i => ({ name: i, value: item_sums[i] })).sort((a,b)=>b.value-a.value).slice(0,5);
            status_chart = new frappe.Chart("#chart-status", {
                data: {
                    labels: top_items.map(i => i.name),
                    datasets: [{ name: __("Overdue Value"), values: top_items.map(i => Math.round(i.value)) }]
                },
                type: "bar", height: 280, colors: ["#e53e3e"]
            });
        }

        // 3. PO Ageing Split Card
        let unique_pos = {};
        data.forEach(row => {
            if (row.po_no && unique_pos[row.po_no] === undefined) {
                unique_pos[row.po_no] = row.ageing_days || 0;
            }
        });
        let ageing_buckets = { "0-15 Days": 0, "15-30 Days": 0, "30-45 Days": 0, "> 45 Days": 0 };
        Object.values(unique_pos).forEach(days => {
            if (days <= 15) ageing_buckets["0-15 Days"]++;
            else if (days <= 30) ageing_buckets["15-30 Days"]++;
            else if (days <= 45) ageing_buckets["30-45 Days"]++;
            else ageing_buckets["> 45 Days"]++;
        });
        let total_pos = Object.keys(unique_pos).length || 1;
        let pct_0_15 = Math.round((ageing_buckets["0-15 Days"] / total_pos) * 100);
        let pct_15_30 = Math.round((ageing_buckets["15-30 Days"] / total_pos) * 100);
        let pct_30_45 = Math.round((ageing_buckets["30-45 Days"] / total_pos) * 100);
        let pct_gt_45 = Math.max(0, 100 - pct_0_15 - pct_15_30 - pct_30_45);

        $("#chart-ageing").html(`
            <div class="stat-split-card">
                <div class="ageing-split-row">
                    <div class="stat-split-item clickable" style="cursor:pointer;" id="stat-ageing-0-15">
                        <div class="stat-split-dot" style="background:#2f855a;"></div>
                        <div class="stat-split-label">0-15 Days</div>
                        <div class="stat-split-num" style="color:#2f855a;">${ageing_buckets["0-15 Days"]}</div>
                        <div class="stat-split-pct">${pct_0_15}%</div>
                    </div>
                    <div class="stat-split-divider"></div>
                    <div class="stat-split-item clickable" style="cursor:pointer;" id="stat-ageing-15-30">
                        <div class="stat-split-dot" style="background:#ecc94b;"></div>
                        <div class="stat-split-label">15-30 Days</div>
                        <div class="stat-split-num" style="color:#ecc94b;">${ageing_buckets["15-30 Days"]}</div>
                        <div class="stat-split-pct">${pct_15_30}%</div>
                    </div>
                    <div class="stat-split-divider"></div>
                    <div class="stat-split-item clickable" style="cursor:pointer;" id="stat-ageing-30-45">
                        <div class="stat-split-dot" style="background:#dd6b20;"></div>
                        <div class="stat-split-label">30-45 Days</div>
                        <div class="stat-split-num" style="color:#dd6b20;">${ageing_buckets["30-45 Days"]}</div>
                        <div class="stat-split-pct">${pct_30_45}%</div>
                    </div>
                    <div class="stat-split-divider"></div>
                    <div class="stat-split-item clickable" style="cursor:pointer;" id="stat-ageing-gt-45">
                        <div class="stat-split-dot" style="background:#e53e3e;"></div>
                        <div class="stat-split-label">&gt; 45 Days</div>
                        <div class="stat-split-num" style="color:#e53e3e;">${ageing_buckets["> 45 Days"]}</div>
                        <div class="stat-split-pct">${pct_gt_45}%</div>
                    </div>
                </div>
                <div class="stat-split-bar">
                    <div style="width:${pct_0_15}%;background:#2f855a;height:100%;"></div>
                    <div style="width:${pct_15_30}%;background:#ecc94b;height:100%;"></div>
                    <div style="width:${pct_30_45}%;background:#dd6b20;height:100%;"></div>
                    <div style="width:${pct_gt_45}%;background:#e53e3e;height:100%;"></div>
                </div>
                <div class="stat-split-total">Total: ${Object.keys(unique_pos).length} POs</div>
            </div>
        `);
        $("#stat-ageing-0-15").on("click", () => { current_ageing_filter = "0-15 Days"; sort_and_render(); });
        $("#stat-ageing-15-30").on("click", () => { current_ageing_filter = "15-30 Days"; sort_and_render(); });
        $("#stat-ageing-30-45").on("click", () => { current_ageing_filter = "30-45 Days"; sort_and_render(); });
        $("#stat-ageing-gt-45").on("click", () => { current_ageing_filter = "> 45 Days"; sort_and_render(); });

        // 4. Billing Status Split Card
        let billing_buckets = { "Not Billed": 0.0, "Partially Billed": 0.0, "Fully Billed": 0.0 };
        data.forEach(row => {
            let billed = row.billed_qty || 0;
            let ordered = row.ordered_qty || 0;
            let val = row.pending_bill_val || 0;
            if (billed === 0) billing_buckets["Not Billed"] += val;
            else if (billed >= ordered) billing_buckets["Fully Billed"] += val;
            else billing_buckets["Partially Billed"] += val;
        });
        let billing_total = Object.values(billing_buckets).reduce((a,b) => a+b, 0) || 1;
        let b_not = billing_buckets["Not Billed"];
        let b_part = billing_buckets["Partially Billed"];
        let b_full = billing_buckets["Fully Billed"];
        let pct_not = Math.round((b_not / billing_total) * 100);
        let pct_part = Math.round((b_part / billing_total) * 100);
        let pct_full = Math.max(0, 100 - pct_not - pct_part);

        $("#chart-billing").html(`
            <div class="stat-split-card">
                <div class="stat-split-row" style="grid-template-columns: 1fr 1px 1fr 1px 1fr;">
                    <div class="stat-split-item clickable" style="cursor:pointer;" id="stat-bill-not">
                        <div class="stat-split-dot" style="background:#e53e3e;"></div>
                        <div class="stat-split-label">Not Billed</div>
                        <div class="stat-split-num" style="color:#e53e3e;font-size:15px;">${format_currency(b_not, current_currency)}</div>
                        <div class="stat-split-pct">${pct_not}%</div>
                    </div>
                    <div class="stat-split-divider"></div>
                    <div class="stat-split-item clickable" style="cursor:pointer;" id="stat-bill-part">
                        <div class="stat-split-dot" style="background:#ecc94b;"></div>
                        <div class="stat-split-label">Partial</div>
                        <div class="stat-split-num" style="color:#b7791f;font-size:15px;">${format_currency(b_part, current_currency)}</div>
                        <div class="stat-split-pct">${pct_part}%</div>
                    </div>
                    <div class="stat-split-divider"></div>
                    <div class="stat-split-item clickable" style="cursor:pointer;" id="stat-bill-full">
                        <div class="stat-split-dot" style="background:#2f855a;"></div>
                        <div class="stat-split-label">Fully Billed</div>
                        <div class="stat-split-num" style="color:#2f855a;font-size:15px;">${format_currency(b_full, current_currency)}</div>
                        <div class="stat-split-pct">${pct_full}%</div>
                    </div>
                </div>
                <div class="stat-split-bar">
                    <div style="width:${pct_not}%;background:#e53e3e;height:100%;border-radius:4px 0 0 4px;"></div>
                    <div style="width:${pct_part}%;background:#ecc94b;height:100%;"></div>
                    <div style="width:${pct_full}%;background:#2f855a;height:100%;border-radius:0 4px 4px 0;"></div>
                </div>
            </div>
        `);
        $("#stat-bill-not").on("click", () => { current_billing_filter = "Not Billed"; sort_and_render(); });
        $("#stat-bill-part").on("click", () => { current_billing_filter = "Partially Billed"; sort_and_render(); });
        $("#stat-bill-full").on("click", () => { current_billing_filter = "Fully Billed"; sort_and_render(); });
    }

    function sort_and_render() {
        po_current_page = 1;
        let search_text = $("#po-search-input").val() ? $("#po-search-input").val().toLowerCase() : "";
        let display_data = report_data.filter(row => {
            return (
                (row.po_no || "").toLowerCase().includes(search_text) ||
                (row.supplier || "").toLowerCase().includes(search_text) ||
                (row.item_code || "").toLowerCase().includes(search_text) ||
                (row.item_name || "").toLowerCase().includes(search_text)
            );
        });

        if (current_ageing_filter) {
            $("#active-ageing-text").text(__("Ageing: ") + current_ageing_filter);
            $("#active-ageing-badge").show();
            display_data = display_data.filter(row => {
                let days = row.ageing_days || 0;
                if (current_ageing_filter === "0-15 Days") return days <= 15;
                if (current_ageing_filter === "15-30 Days") return days > 15 && days <= 30;
                if (current_ageing_filter === "30-45 Days") return days > 30 && days <= 45;
                if (current_ageing_filter === "> 45 Days") return days > 45;
                return true;
            });
        } else {
            $("#active-ageing-badge").hide();
        }

        if (current_billing_filter) {
            $("#active-billing-text").text(__("Billing: ") + current_billing_filter);
            $("#active-billing-badge").show();
            display_data = display_data.filter(row => {
                let billed = row.billed_qty || 0;
                let ordered = row.ordered_qty || 0;
                if (current_billing_filter === "Not Billed") return billed === 0;
                if (current_billing_filter === "Partially Billed") return billed > 0 && billed < ordered;
                if (current_billing_filter === "Fully Billed") return billed >= ordered;
                return true;
            });
        } else {
            $("#active-billing-badge").hide();
        }

        display_data.sort((a, b) => {
            let valA = a[current_sort.key] ?? "";
            let valB = b[current_sort.key] ?? "";
            if (typeof valA === "string") valA = valA.toLowerCase();
            if (typeof valB === "string") valB = valB.toLowerCase();
            if (valA < valB) return current_sort.asc ? -1 : 1;
            if (valA > valB) return current_sort.asc ? 1 : -1;
            return 0;
        });

        render_table(display_data);
    }

    function render_table(filtered_table_data) {
        let tbody = $("#po-table-body");
        tbody.empty();
        
        let total_count = filtered_table_data.length;
        $("#results-count").text(__("Showing ") + total_count + __(" items"));

        if (total_count === 0) {
            tbody.append(`<tr><td colspan="14" class="text-center text-muted" style="padding:40px;">${__("No matching records found")}</td></tr>`);
            return;
        }

        let start_idx = (po_current_page - 1) * po_page_size;
        let end_idx = Math.min(start_idx + po_page_size, total_count);
        let page_data = filtered_table_data.slice(start_idx, end_idx);

        page_data.forEach(row => {
            let row_class = row.is_overdue ? "row-overdue" : "";
            tbody.append(`
                <tr class="${row_class}">
                    <td><a class="document-link po-link" data-po="${row.po_no}">${row.po_no}</a></td>
                    <td>${frappe.datetime.str_to_user(row.po_date)}</td>
                    <td class="text-right ${row.ageing_days > 45 ? 'text-danger font-weight-bold' : ''}">
                        ${row.ageing_days}
                    </td>
                    <td>
                        <div class="date-container">
                            <span>${frappe.datetime.str_to_user(row.required_date)}</span>
                            ${row.is_overdue ? '<span class="badge badge-danger">Overdue</span>' : ''}
                        </div>
                    </td>
                    <td><a class="document-link supplier-link" data-supplier="${row.supplier}">${row.supplier}</a></td>
                    <td><a class="document-link item-link" data-item="${row.item_code}">${row.item_code}</a></td>
                    <td>${row.item_name || ""}</td>
                    <td class="text-right">${fmt_float(row.ordered_qty)}</td>
                    <td class="text-right font-weight-bold ${row.outstanding_qty > 0 ? 'text-primary' : ''}">
                        ${fmt_float(row.outstanding_qty)}
                    </td>
                    <td class="text-right">${fmt_float(row.billed_qty)}</td>
                    <td class="text-right font-weight-bold ${row.pending_billed_qty > 0 ? 'text-warning' : ''}">
                        ${fmt_float(row.pending_billed_qty)}
                    </td>
                    <td class="text-right font-weight-bold ${row.pending_bill_val > 0 ? 'text-warning' : ''}">
                        ${format_currency(row.pending_bill_val || 0, current_currency)}
                    </td>
                    <td class="text-right">${format_currency(row.rate, current_currency)}</td>
                    <td class="text-right font-weight-bold">${format_currency(row.amount, current_currency)}</td>
                </tr>
            `);
        });
    }

    $("#po-table th").on("click", function() {
        let key = $(this).attr("data-sort");
        if (!key) return;
        current_sort.asc = (current_sort.key === key) ? !current_sort.asc : true;
        current_sort.key = key;
        sort_and_render();
    });
    
    $("#po-search-input").on("keyup", function() { sort_and_render(); });

    main_container.on("click", ".po-link", function() {
        frappe.set_route("Form", "Purchase Order", $(this).attr("data-po"));
    });
    main_container.on("click", ".supplier-link", function() {
        frappe.set_route("Form", "Supplier", $(this).attr("data-supplier"));
    });
    main_container.on("click", ".item-link", function() {
        frappe.set_route("Form", "Item", $(this).attr("data-item"));
    });
    main_container.on("click", "#active-ageing-badge", function() {
        current_ageing_filter = null;
        sort_and_render();
    });
    main_container.on("click", "#active-billing-badge", function() {
        current_billing_filter = null;
        sort_and_render();
    });
    
    function format_currency(val, currency) {
        let num = parseFloat(val || 0).toLocaleString("en-IN", {
            minimumFractionDigits: 2, maximumFractionDigits: 2
        });
        return (currency || "INR") + " " + num;
    }

    function format_currency_html(val, currency) {
        let num = parseFloat(val || 0).toLocaleString("en-IN", {
            minimumFractionDigits: 2, maximumFractionDigits: 2
        });
        return `<span class="kpi-sym">${currency || "INR"}</span> <span>${num}</span>`;
    }

    function fmt_float(val) {
        return parseFloat(val || 0).toLocaleString("en-IN", {
            minimumFractionDigits: 2, maximumFractionDigits: 2
        });
    }

    function export_to_csv() {
        let csv = [];
        let headers = ["PO Number", "PO Date", "Ageing (Days)", "Expected Date", "Supplier", "Item Code", "Item Name", "Ordered Qty", "Pending Qty", "Billed Qty", "Pending Bill Qty", "Pending Bill Value", "Rate", "Amount"];
        csv.push(headers.join(","));
        
        report_data.forEach(row => {
            let line = [
                `"${row.po_no}"`,
                `"${row.po_date}"`,
                row.ageing_days,
                `"${row.required_date}"`,
                `"${(row.supplier||'').replace(/"/g, '""')}"`,
                `"${row.item_code}"`,
                `"${(row.item_name||'').replace(/"/g, '""')}"`,
                row.ordered_qty,
                row.outstanding_qty,
                row.billed_qty,
                row.pending_billed_qty,
                (row.pending_bill_val || 0).toFixed(2),
                row.rate,
                row.amount
            ];
            csv.push(line.join(","));
        });
        
        let csv_string = csv.join("\n");
        let filename = `open_purchase_orders_${frappe.datetime.get_today()}.csv`;
        let link = document.createElement("a");
        link.setAttribute("href", "data:text/csv;charset=utf-8," + encodeURIComponent(csv_string));
        link.setAttribute("download", filename);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
    
    // Initial load
    refresh_data();
};
