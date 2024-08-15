// Copyright (c) 2023, 4C Solutions and contributors
// For license information, please see license.txt
frappe.provide('erpnext.queries');
frappe.require("/assets/erpnext/js/projects/timer.js", function(){
	console.log("Timer script loaded.");
});
frappe.ui.form.on('Customer Appointment', {
	setup: function(frm) {
		frm.custom_make_buttons = {
			'Timesheet': 'Timesheet'
		};
	},

	onload: function(frm) {
		if (frm.is_new()) {
			frm.set_value('appointment_time', null);
			frm.disable_save();
		}
	},

	refresh: function(frm) {
		frm.set_query('customer', () => {
			return {
				filters: { 'disabled': 0 }
			};
		});

		frm.set_query('matter', () => {
			if (frm.doc.customer) {
				return {
					filters: { 'customer': frm.doc.customer }
				};
			}
		});

		frm.set_query('case', () => {
			if (frm.doc.customer) {
				return {
					filters: { 'customer': frm.doc.customer }
				};
			}
		});

		if (frm.is_new()) {
			frm.page.set_primary_action(__('Check Availability'), function() {
				if (!frm.doc.customer) {
					frappe.msgprint({
						title: __('Not Allowed'),
						message: __('Please select Customer first'),
						indicator: 'red'
					});
				} else {
					check_and_set_availability(frm);
				}
			});
		} else {
			frm.page.set_primary_action(__('Save'), () => frm.save());
		}

		if (frm.doc.status == 'Open' || (frm.doc.status == 'Scheduled' && !frm.doc.__islocal)) {
			frm.add_custom_button(__('Cancel'), function() {
				update_status(frm, 'Cancelled');
			});
			frm.add_custom_button(__('Reschedule'), function() {
				check_and_set_availability(frm);
			});

			frm.add_custom_button(__('Start'), function() {
				frappe.call({
					method: 'casecentral.case_central.doctype.customer_appointment.customer_appointment.make_timesheet',
					args: {
						source_name: frm.doc.name
					},
					callback: function(response) {
						var new_doc = response.message;
						if (new_doc && new_doc.doctype === 'Timesheet') {
							// Set up initial conditions for the timer
							if (!new_doc.time_logs || new_doc.time_logs.length === 0) {
								new_doc.time_logs = [{
									activity_type: "Consultation",
									from_time: null,
									to_time: null,
									hours: 0
								}];
							}
							save_and_open_timesheet(new_doc);
						} else {
							console.error('Response is not a Timesheet or message is missing:', response);
						}
					}
				});
			}).addClass("btn-primary");
		}
	}
});

function save_and_open_timesheet(new_doc) {
	frappe.call({
		method: 'frappe.client.save',
		args: {
			doc: new_doc
		},
		callback: function(response) {
			var new_doc_saved = response.message;
			// Redirect to the Timesheet form and start the timer
			frappe.set_route('Form', 'Timesheet', new_doc_saved.name).then(function() {
				frappe.ui.form.on('Timesheet', {
					onload: function(frm) {
						startTimer(frm);
					}
				});
			});
		}
	});
}

function startTimer(frm) {
	var flag = true;
	$.each(frm.doc.time_logs || [], function (i, row) {
		// Fetch the row for which from_time is not present
		if (flag && row.activity_type && !row.from_time) {
			erpnext.timesheet.timer(frm, row);
			row.from_time = frappe.datetime.now_datetime();
			frm.refresh_fields("time_logs");
			frm.save();
			flag = false;
		}
		// Fetch the row for timer where activity is not completed and from_time is before now_time
		if (flag && row.from_time <= frappe.datetime.now_datetime() && !row.completed) {
			let timestamp = moment(frappe.datetime.now_datetime()).diff(
				moment(row.from_time),
				"seconds"
			);
			erpnext.timesheet.timer(frm, row, timestamp);
			flag = false;
		}
	});
	// If no activities found to start a timer, create new
	if (flag) {
		erpnext.timesheet.timer(frm, row);
	}
}

let check_and_set_availability = function(frm) {
	let selected_slot = null;
	let meeting_room = null;
	let duration = null;
	let add_video_conferencing = null;
	let overlap_appointments = null;

	show_availability();

	function show_empty_state(employee, appointment_date) {
		frappe.msgprint({
			title: __('Not Available'),
			message: __('Employee {0} not available on {1}', [employee.bold(), appointment_date.bold()]),
			indicator: 'red'
		});
	}

	function show_availability() {
		let selected_employee = '';
		let d = new frappe.ui.Dialog({
			title: __('Available slots'),
			fields: [
				{ fieldtype: 'Link', options: 'Employee', reqd: 1, fieldname: 'employee', label: 'Employee' },
				{ fieldtype: 'Column Break' },
				{ fieldtype: 'Date', reqd: 1, fieldname: 'appointment_date', label: 'Date', min_date: new Date(frappe.datetime.get_today()), default: frappe.datetime.get_today() },
				{ fieldtype: 'Section Break' },
				{ fieldtype: 'HTML', fieldname: 'available_slots' }

			],
			primary_action_label: __('Book'),
			primary_action: function() {
				frm.set_value('appointment_time', selected_slot);
				add_video_conferencing = add_video_conferencing && !d.$wrapper.find(".opt-out-check").is(":checked")
					&& !overlap_appointments

				frm.set_value('add_video_conferencing', add_video_conferencing);

				if (!frm.doc.duration) {
					frm.set_value('duration', duration);
				}

				frm.set_value('employee', d.get_value('employee'));
				frm.set_value('appointment_date', d.get_value('appointment_date'));

				if (meeting_room) {
					frm.set_value('meeting_room', meeting_room);
				}

				d.hide();
				frm.enable_save();
				frm.save();
				d.get_primary_btn().attr('disabled', true);
			}
		});

		d.set_values({
			'employee': frm.doc.employee,
			'appointment_date': frm.doc.appointment_date
		});

		// disable dialog action initially
		d.get_primary_btn().attr('disabled', true);

		// Field Change Handler

		let fd = d.fields_dict;

		d.fields_dict['appointment_date'].df.onchange = () => {
			show_slots(d, fd);
		};
		d.fields_dict['employee'].df.onchange = () => {
			if (d.get_value('employee') && d.get_value('employee') != selected_employee) {
				selected_employee = d.get_value('employee');
				show_slots(d, fd);
			}
		};

		d.show();
	}

	function show_slots(d, fd) {
		if (d.get_value('appointment_date') && d.get_value('employee')) {
			fd.available_slots.html('');
			frappe.call({
				method: 'casecentral.case_central.doctype.customer_appointment.customer_appointment.get_availability_data',
				args: {
					employee: d.get_value('employee'),
					date: d.get_value('appointment_date')
				},
				callback: (r) => {
					let data = r.message;
					if (data.slot_details.length > 0) {
						let $wrapper = d.fields_dict.available_slots.$wrapper;

						// make buttons for each slot
						let slot_html = get_slots(data.slot_details, d.get_value('appointment_date'));

						$wrapper
							.css('margin-bottom', 0)
							.addClass('text-center')
							.html(slot_html);

						// highlight button when clicked
						$wrapper.on('click', 'button', function() {
							let $btn = $(this);
							$wrapper.find('button').removeClass('btn-outline-primary');
							$btn.addClass('btn-outline-primary');
							selected_slot = $btn.attr('data-name');
							meeting_room = $btn.attr('data-meeting-room');
							duration = $btn.attr('data-duration');
							add_video_conferencing = parseInt($btn.attr('data-tele-conf'));
							overlap_appointments = parseInt($btn.attr('data-overlap-appointments'));
							// show option to opt out of tele conferencing
							if ($btn.attr('data-tele-conf') == 1) {
								if (d.$wrapper.find(".opt-out-conf-div").length) {
									d.$wrapper.find(".opt-out-conf-div").show();
								} else {
									overlap_appointments ?
										d.footer.prepend(
											`<div class="opt-out-conf-div ellipsis text-muted" style="vertical-align:text-bottom;">
												<label>
													<span class="label-area">
													${__("Video Conferencing disabled for group consultations")}
													</span>
												</label>
											</div>`
										)
									:
										d.footer.prepend(
											`<div class="opt-out-conf-div ellipsis" style="vertical-align:text-bottom;">
											<label>
												<input type="checkbox" class="opt-out-check"/>
												<span class="label-area">
												${__("Do not add Video Conferencing")}
												</span>
											</label>
										</div>`
										);
								}
							} else {
								d.$wrapper.find(".opt-out-conf-div").hide();
							}

							// enable primary action 'Book'
							d.get_primary_btn().attr('disabled', null);
						});

					} else {
						//	fd.available_slots.html('Please select a valid date.'.bold())
						show_empty_state(d.get_value('employee'), d.get_value('appointment_date'));
					}
				},
				freeze: true,
				freeze_message: __('Fetching Schedule...')
			});
		} else {
			fd.available_slots.html(__('Appointment date and Employee are Mandatory').bold());
		}
	}

	function get_slots(slot_details, appointment_date) {
		let slot_html = '';
		let appointment_count = 0;
		let disabled = false;
		let start_str, slot_start_time, slot_end_time, interval, count, count_class, tool_tip, available_slots;

		slot_details.forEach((slot_info) => {
			slot_html += `<div class="slot-info">
				<span><b>
				${__('Employee Schedule: ')} </b> ${slot_info.slot_name}
					${slot_info.tele_conf && !slot_info.allow_overlap ? '<i class="fa fa-video-camera fa-1x" aria-hidden="true"></i>' : ''}
				</span><br>
				<span><b> ${__('Meeting Room: ')} </b> ${slot_info.meeting_room}</span>`;

			if (slot_info.meeting_room_capacity) {
				slot_html += `<br><span> <b> ${__('Maximum Capacity:')} </b> ${slot_info.meeting_room_capacity} </span>`;
			}

			slot_html += '</div><br>';

			slot_html += slot_info.avail_slot.map(slot => {
				appointment_count = 0;
				disabled = false;
				count_class = tool_tip = '';
				start_str = slot.from_time;
				slot_start_time = moment(slot.from_time, 'HH:mm:ss');
				slot_end_time = moment(slot.to_time, 'HH:mm:ss');
				interval = (slot_end_time - slot_start_time) / 60000 | 0;

				// restrict past slots based on the current time.
				let now = moment();
				if((now.format("YYYY-MM-DD") == appointment_date) && slot_start_time.isBefore(now)){
					disabled = true;
				} else {
					// iterate in all booked appointments, update the start time and duration
					slot_info.appointments.forEach((booked) => {
						let booked_moment = moment(booked.appointment_time, 'HH:mm:ss');
						let end_time = booked_moment.clone().add(booked.duration, 'minutes');

						// Deal with 0 duration appointments
						if (booked_moment.isSame(slot_start_time) || booked_moment.isBetween(slot_start_time, slot_end_time)) {
							if (booked.duration == 0) {
								disabled = true;
								return false;
							}
						}

						// Check for overlaps considering appointment duration
						if (slot_info.allow_overlap != 1) {
							if (slot_start_time.isBefore(end_time) && slot_end_time.isAfter(booked_moment)) {
								// There is an overlap
								disabled = true;
								return false;
							}
						} else {
							if (slot_start_time.isBefore(end_time) && slot_end_time.isAfter(booked_moment)) {
								appointment_count++;
							}
							if (appointment_count >= slot_info.meeting_room_capacity) {
								// There is an overlap
								disabled = true;
								return false;
							}
						}
					});
				}

				if (slot_info.allow_overlap == 1 && slot_info.meeting_room_capacity > 1) {
					available_slots = slot_info.meeting_room_capacity - appointment_count;
					count = `${(available_slots > 0 ? available_slots : __('Full'))}`;
					count_class = `${(available_slots > 0 ? 'badge-success' : 'badge-danger')}`;
					tool_tip =`${available_slots} ${__('slots available for booking')}`;
				}

				return `
					<button class="btn btn-secondary" data-name=${start_str}
						data-duration=${interval}
						data-meeting-room="${slot_info.meeting_room || ''}"
						data-tele-conf="${slot_info.tele_conf || 0}"
						data-overlap-appointments="${slot_info.meeting_room_capacity || 0}"
						style="margin: 0 10px 10px 0; width: auto;" ${disabled ? 'disabled="disabled"' : ""}
						data-toggle="tooltip" title="${tool_tip || ''}">
						${start_str.substring(0, start_str.length - 3)}
						${slot_info.meeting_room_capacity ? `<br><span class='badge ${count_class}'> ${count} </span>` : ''}
					</button>`;

			}).join("");

			if (slot_info.meeting_room_capacity) {
				slot_html += `<br/><small>${__('Each slot indicates the capacity currently available for booking')}</small>`;
			}
			slot_html += `<br/><br/>`;
		});

		return slot_html;
	}
};

let update_status = function(frm, status) {
	let doc = frm.doc;
	frappe.confirm(__('Are you sure you want to cancel this appointment?'),
		function() {
			frappe.call({
				method: 'casecentral.case_central.doctype.customer_appointment.customer_appointment.update_status',
				args: { appointment_id: doc.name, status: status },
				callback: function(data) {
					if (!data.exc) {
						frm.reload_doc();
					}
				}
			});
		}
	);
};
