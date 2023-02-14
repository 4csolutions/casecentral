frappe.ui.form.on('Sales Invoice', {
    refresh: function(frm) {
		if (cint(frm.doc.docstatus==0) && cur_frm.page.current_view_name!=="pos" && !frm.doc.is_return) {
            frm.add_custom_button(__('Legal Services'), function() {
                get_legal_services_to_invoice(frm);
            },__("Get Items From"));
        }
    }
});

var get_legal_services_to_invoice = function(frm) {
	var me = this;
    let selected_matter = '';
	var dialog = new frappe.ui.Dialog({
		title: __("Get Items from Legal Services"),
		fields:[
			{
				fieldtype: 'Link',
				options: 'Matter',
				label: 'Matter',
				fieldname: "matter",
				reqd: true
			},
			{ fieldtype: 'Section Break'	},
			{ fieldtype: 'HTML', fieldname: 'results_area' }
		]
	});
	var $wrapper;
	var $results;
	var $placeholder;
	dialog.set_values({
		'matter': frm.doc.matter
	});
	dialog.fields_dict["matter"].df.onchange = () => {
		var matter = dialog.fields_dict.matter.input.value;
		if(matter && matter!=selected_matter){
			selected_matter = matter;
			var method = "casecentral.utils.get_legal_services_to_invoice";
			var args = {matter: matter, company: frm.doc.company};
			var columns = (["service", "reference_name", "reference_type"]);
			get_legal_service_items(frm, $results, $placeholder, method, args, columns);
		}
		else if(!matter){
			selected_matter = '';
			$results.empty();
			$results.append($placeholder);
		}
	}
	$wrapper = dialog.fields_dict.results_area.$wrapper.append(`<div class="results"
		style="border: 1px solid #d1d8dd; border-radius: 3px; height: 300px; overflow: auto;"></div>`);
	$results = $wrapper.find('.results');
	$placeholder = $(`<div class="multiselect-empty-state">
				<span class="text-center" style="margin-top: -40px;">
					<i class="fa fa-2x fa-heartbeat text-extra-muted"></i>
					<p class="text-extra-muted">No billable Legal Services found</p>
				</span>
			</div>`);
	$results.on('click', '.list-item--head :checkbox', (e) => {
		$results.find('.list-item-container .list-row-check')
			.prop("checked", ($(e.target).is(':checked')));
	});
	set_primary_action(frm, dialog, $results);
	dialog.show();
};

var get_legal_service_items = function(frm, $results, $placeholder, method, args, columns) {
	var me = this;
	$results.empty();
	frappe.call({
		method: method,
		args: args,
		callback: function(data) {
			if(data.message){
				$results.append(make_list_row(columns));
				for(let i=0; i<data.message.length; i++){
					$results.append(make_list_row(columns, data.message[i]));
				}
			}else {
				$results.append($placeholder);
			}
		}
	});
}

var make_list_row= function(columns, result={}) {
	var me = this;
	// Make a head row by default (if result not passed)
	let head = Object.keys(result).length === 0;
	let contents = ``;
	columns.forEach(function(column) {
		contents += `<div class="list-item__content ellipsis">
			${
				head ? `<span class="ellipsis">${__(frappe.model.unscrub(column))}</span>`

				:(column !== "name" ? `<span class="ellipsis">${__(result[column])}</span>`
					: `<a class="list-id ellipsis">
						${__(result[column])}</a>`)
			}
		</div>`;
	})

	let $row = $(`<div class="list-item">
		<div class="list-item__content" style="flex: 0 0 10px;">
			<input type="checkbox" class="list-row-check" ${result.checked ? 'checked' : ''}>
		</div>
		${contents}
	</div>`);

	$row = list_row_data_items(head, $row, result);
	return $row;
};

var set_primary_action= function(frm, dialog, $results) {
	var me = this;
	dialog.set_primary_action(__('Add'), function() {
		let checked_values = get_checked_values($results);
		if(checked_values.length > 0){
            if ( !frm.doc.matter ) {
                frm.set_value("matter", dialog.fields_dict.matter.input.value);
            }
			frm.set_value("items", []);
			add_to_item_line(frm, checked_values);
			dialog.hide();
		}
		else {
			frappe.msgprint(__("Please select Legal Service"));
		}
	});
};

var get_checked_values= function($results) {
	return $results.find('.list-item-container').map(function() {
		let checked_values = {};
		if ($(this).find('.list-row-check:checkbox:checked').length > 0 ) {
			checked_values['dn'] = $(this).attr('data-dn');
			checked_values['dt'] = $(this).attr('data-dt');
			checked_values['item'] = $(this).attr('data-item');
			if($(this).attr('data-rate') != 'undefined'){
				checked_values['rate'] = $(this).attr('data-rate');
			}
			else{
				checked_values['rate'] = false;
			}
			if($(this).attr('data-income-account') != 'undefined'){
				checked_values['income_account'] = $(this).attr('data-income-account');
			}
			else{
				checked_values['income_account'] = false;
			}
			if($(this).attr('data-qty') != 'undefined'){
				checked_values['qty'] = $(this).attr('data-qty');
			}
			else{
				checked_values['qty'] = false;
			}
			if($(this).attr('data-description') != 'undefined'){
				checked_values['description'] = $(this).attr('data-description');
			}
			else{
				checked_values['description'] = false;
			}
			return checked_values;
		}
	}).get();
};

var list_row_data_items = function(head, $row, result) {
    head ? $row.addClass('list-item--head')
        : $row = $(`<div class="list-item-container"
            data-dn= "${result.reference_name}" data-dt= "${result.reference_type}" data-item= "${result.service}"
            data-rate = ${result.rate}
            data-income-account = "${result.income_account}"
            data-qty = ${result.qty}
            data-description = "${result.description}">
            </div>`).append($row);
	return $row
};

var add_to_item_line = function(frm, checked_values){
    console.log(frm.doc);
    frappe.call({
        doc: frm.doc,
        method: "set_legal_services",
        args:{ checked_values: checked_values },
        callback: function() {
            frm.trigger("validate");
            frm.refresh_fields();
        }
    });
};