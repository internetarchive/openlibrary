import datetime

import web
from infogami.utils.view import render_template

from openlibrary.core import support

support_db = None

class cases(object):
    def GET(self, typ = "all"):
        if not support_db:
            return render_template("admin/cases", None, None, True)
        cases = support_db.get_all_cases(typ)
        summary = support_db.get_all_cases(typ, summarise = True)
        return render_template("admin/cases", summary, cases)

class case(object):
    def GET(self, caseid):
        if not support_db:
            return render_template("admin/cases", None, None, True)
        case = support_db.get_case(caseid)
        date_pretty_printer = lambda x: x.strftime("%B %d, %Y")
        return render_template("admin/case", case, date_pretty_printer)

    def POST(self, caseid):
        if not support_db:
            return render_template("admin/cases", None, None, True)
        case = support_db.get_case(caseid)
        form = web.input()
        action = form.get("button","")
        {"SEND REPLY" : self.POST_sendreply,
         "UPDATE"     : self.POST_update,
         "CLOSE CASE" : self.POST_closecase}[action](form,case)
        date_pretty_printer = lambda x: x.strftime("%B %d, %Y")
        return render_template("admin/case", case, date_pretty_printer, True)
    
    def POST_sendreply(self, form, case):
        user = web.ctx.site.get_user()
        casenote = form.get("casenote1", False)
        email_to = form.get("email", False)
        case.add_worklog_entry(by = user.get_email(),
                               text = casenote or "No note entered")
        case.change_status("replied", user.get_email())
        if email_to:
            print "Send email to %s"%email_to
        import pdb;pdb.set_trace()
        # web.sendmail(email_to, config.report_spam_address, msg.subject, str(msg))
        # print config.report_spam_address



    def POST_update(self, form, case):
        casenote = form.get("casenote2", False)
        assignee = form.get("assignee", False)
        user = web.ctx.site.get_user()
        by = user.get_email()
        text = casenote or "No note entered"
        if assignee != case.assignee:
            text += "\n<br/>Case reassigned to %s"%assignee
        case.add_worklog_entry(by = by,
                               text = text)


    def POST_closecase(self, form, case):
        user = web.ctx.site.get_user()
        by = user.get_email()
        text = "Case closed"
        case.add_worklog_entry(by = by,
                               text = text)
        case.change_status("closed", by)

def setup():
    global support_db
    try:
        support_db = support.Support()
    except support.DatabaseConnectionError:
        support_db = None


