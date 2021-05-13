# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import comma_sep, comma_and, getdate, today, add_months, add_days
from erpnext.hr.doctype.employee.employee import get_all_employee_emails, get_employee_email, is_holiday, get_holiday_list_for_employee
from erpnext.hr.utils import get_holidays_for_employee

# -----------------
# HOLIDAY REMINDERS
# -----------------
def send_holiday_reminders():
	"""
		Send holiday reminders to Employees if 'Send Holiday Reminders' is checked
	"""
	to_send = int(frappe.db.get_single_value("HR Settings", "send_holiday_reminders") or 1)
	if not to_send:
		return
	
	employees = frappe.db.get_all('Employee', pluck='name')

	for employee in employees:
		has_holiday, holiday_descriptions = is_holiday(employee, only_non_weekly=True, with_description=True, raise_exception=False)
		if has_holiday:
			send_holiday_reminder_to_employee(employee, holiday_descriptions)

def send_holiday_reminder_to_employee(employee, descriptions):
	reminder_text, message = get_holiday_reminder_text_and_message(descriptions)
	
	employee_doc = frappe.get_doc('Employee', employee)
	employee_email = get_employee_email(employee_doc)

	frappe.sendmail(
		recipients=[employee_email],
		subject=_("Holiday Reminder"),
		template="holiday_reminder",
		args=dict(
			reminder_text=reminder_text,
			message=message
		),
		header=_("Today is a holiday for you.")
	)

def get_holiday_reminder_text_and_message(descriptions):
	description = descriptions[0] if len(descriptions) == 1 else comma_and(descriptions, add_quotes=False)
	
	reminder_text = _("This email is to remind you about today's holiday.")
	message = _("Holiday is on the occassion of {0}.").format(description)

	return reminder_text, message


# ------------------
# BIRTHDAY REMINDERS
# ------------------
def send_birthday_reminders():
	"""Send Employee birthday reminders if no 'Stop Birthday Reminders' is not set."""
	if int(frappe.db.get_single_value("HR Settings", "stop_birthday_reminders") or 0):
		return

	employees_born_today = get_employees_who_are_born_today()

	for company, birthday_persons in employees_born_today.items():
		employee_emails = get_all_employee_emails(company)
		birthday_person_emails = [get_employee_email(doc) for doc in birthday_persons]
		recipients = list(set(employee_emails) - set(birthday_person_emails))

		reminder_text, message = get_birthday_reminder_text_and_message(birthday_persons)
		send_birthday_reminder(recipients, reminder_text, birthday_persons, message)

		if len(birthday_persons) > 1:
			# special email for people sharing birthdays
			for person in birthday_persons:
				person_email = person["user_id"] or person["personal_email"] or person["company_email"]
				others = [d for d in birthday_persons if d != person]
				reminder_text, message = get_birthday_reminder_text_and_message(others)
				send_birthday_reminder(person_email, reminder_text, others, message)

def get_birthday_reminder_text_and_message(birthday_persons):
	if len(birthday_persons) == 1:
		birthday_person_text = birthday_persons[0]['name']
	else:
		# converts ["Jim", "Rim", "Dim"] to Jim, Rim & Dim
		person_names = [d['name'] for d in birthday_persons]
		birthday_person_text = comma_sep(person_names, frappe._("{0} & {1}"), False)

	reminder_text = _("Today is {0}'s birthday 🎉").format(birthday_person_text)
	message = _("A friendly reminder of an important date for our team.")
	message += "<br>"
	message += _("Everyone, let’s congratulate {0} on their birthday.").format(birthday_person_text)

	return reminder_text, message

def send_birthday_reminder(recipients, reminder_text, birthday_persons, message):
	frappe.sendmail(
		recipients=recipients,
		subject=_("Birthday Reminder"),
		template="birthday_reminder",
		args=dict(
			reminder_text=reminder_text,
			birthday_persons=birthday_persons,
			message=message,
		),
		header=_("Birthday Reminder 🎂")
	)

def get_employees_who_are_born_today():
	"""Get all employee born today & group them based on their company"""
	return get_employees_having_an_event_today("birthday") 

def get_employees_having_an_event_today(event_type):
	"""Get all employee who have `event_type` today 
	& group them based on their company. `event_type`
	can be `birthday` or `work_anniversary`"""

	from collections import defaultdict

	# Set column based on event type
	if event_type == 'birthday':
		condition_column = 'date_of_birth'
	elif event_type == 'work_anniversary':
		condition_column = 'date_of_joining'
	else:
		return

	employees_born_today = frappe.db.multisql({
		"mariadb": f"""
			SELECT `personal_email`, `company`, `company_email`, `user_id`, `employee_name` AS 'name', `image`, `date_of_joining`
			FROM `tabEmployee`
			WHERE
				DAY({condition_column}) = DAY(%(today)s)
			AND
				MONTH({condition_column}) = MONTH(%(today)s)
			AND
				`status` = 'Active'
		""",
		"postgres": f"""
			SELECT "personal_email", "company", "company_email", "user_id", "employee_name" AS 'name', "image"
			FROM "tabEmployee"
			WHERE
				DATE_PART('day', {condition_column}) = date_part('day', %(today)s)
			AND
				DATE_PART('month', {condition_column}) = date_part('month', %(today)s)
			AND
				"status" = 'Active'
		""",
	}, dict(today=today(), condition_column=condition_column), as_dict=1)

	grouped_employees = defaultdict(lambda: [])

	for employee_doc in employees_born_today:
		grouped_employees[employee_doc.get('company')].append(employee_doc)

	return grouped_employees


# --------------------------
# WORK ANNIVERSARY REMINDERS
# --------------------------
def send_work_anniversary_reminders():
	"""Send Employee Work Anniversary Reminders if 'Send Work Anniversary Reminders' is checked"""
	to_send = int(frappe.db.get_single_value("HR Settings", "send_work_anniversary_reminders") or 1) 
	if not to_send:
		return
	
	employees_joined_today = get_employees_having_an_event_today("work_anniversary")

	for company, anniversary_persons in employees_joined_today.items():
		employee_emails = get_all_employee_emails(company)
		anniversary_person_emails = [get_employee_email(doc) for doc in anniversary_persons]
		recipients = list(set(employee_emails) - set(anniversary_person_emails))

		reminder_text, message = get_work_anniversary_reminder_text_and_message(anniversary_persons)		
		send_work_anniversary_reminder(recipients, reminder_text, anniversary_persons, message)

		if len(anniversary_persons) > 1:
			# email for people sharing work anniversaries
			for person in anniversary_persons:
				person_email = person["user_id"] or person["personal_email"] or person["company_email"]	
				others = [d for d in anniversary_persons if d != person]
				reminder_text, message = get_work_anniversary_reminder_text_and_message(others)
				send_work_anniversary_reminder(person_email, reminder_text, others, message)

def get_work_anniversary_reminder_text_and_message(anniversary_persons):
	if len(anniversary_persons) == 1:
		anniversary_person = anniversary_persons[0]['name']
		# Number of years completed at the company
		completed_years = getdate().year - anniversary_persons[0]['date_of_joining'].year
		anniversary_person += f" completed {completed_years} years"
	else:
		person_names_with_years = []
		for person in anniversary_persons:
			person_text = person['name']
			# Number of years completed at the company
			completed_years = getdate().year - person['date_of_joining'].year
			person_text += f" completed {completed_years} years"
			person_names_with_years.append(person_text)

		# converts ["Jim", "Rim", "Dim"] to Jim, Rim & Dim
		anniversary_person = comma_sep(person_names_with_years, frappe._("{0} & {1}"), False)

	reminder_text = _("Today {0} at our Company! 🎉").format(anniversary_person)
	message = _("A friendly reminder of an important date for our team.")
	message += "<br>"
	message += _("Everyone, let’s congratulate {0} on their work anniversary!").format(anniversary_person)

	return reminder_text, message

def send_work_anniversary_reminder(recipients, reminder_text, anniversary_persons, message):
	frappe.sendmail(
		recipients=recipients,
		subject=_("Work Anniversary Reminder"),
		template="anniversary_reminder",
		args=dict(
			reminder_text=reminder_text,
			anniversary_persons=anniversary_persons,
			message=message,
		),
		header=_("🎊️🎊️ Work Anniversary Reminder 🎊️🎊️")
	)


# ----------------------------------
# ADVANCE HOLIDAY REMINDERS
# ----------------------------------
def send_reminders_in_advance_weekly():
	to_send_in_advance = int(frappe.db.get_single_value("HR Settings", "send_holiday_reminders_in_advance") or 1) 
	frequency = frappe.db.get_single_value("HR Settings", "frequency")
	if not (to_send_in_advance and frequency == "Weekly"):
		return

	send_advance_holiday_reminders("Weekly")

def send_reminders_in_advance_monthly():
	to_send_in_advance = int(frappe.db.get_single_value("HR Settings", "send_holiday_reminders_in_advance") or 1) 
	frequency = frappe.db.get_single_value("HR Settings", "frequency")
	if not (to_send_in_advance and frequency == "Monthly"):
		return

	send_advance_holiday_reminders("Monthly")

def send_advance_holiday_reminders(frequency):
	"""Send Holiday Reminders in Advance to Employees
	`frequency` (str): 'Weekly' or 'Monthly'
	"""
	if frequency == "Weekly":
		start_date = add_days(getdate(), 1)
		end_date = add_days(getdate(), 7)
	elif frequency == "Monthly":
		# Sent on 1st of every month
		start_date = add_days(getdate())
		end_date = add_months(getdate(), 1)
	else:
		return 

	employees = frappe.db.get_all('Employee', pluck='name')
	for employee in employees:
		holidays = get_holidays_for_employee(
			start_date, end_date, 
			only_non_weekly=True, 
			raise_exception=False
		)
		
		if not (holidays is None):
			send_holidays_reminder_in_advance(employee, holidays)

def send_holidays_reminder_in_advance(employee, holidays):
	pass