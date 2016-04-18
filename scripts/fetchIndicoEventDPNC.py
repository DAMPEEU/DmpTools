"""
@author: 	S. Zimmer (Geneva)
@brief: 	convenience script to crawl DPNC Indico page and extract all contributions for each event with identical names
@note:		this version crawls subcontributions and creates links manually rather than extracting the full metadata
@note: 		since the server has a self-signed certificate, ssl verification is bypassed using a context; 
			see http://stackoverflow.com/questions/27835619/ssl-certificate-verify-failed-error
"""

import time, datetime, json, urllib, ssl

GLOB_API_KEY = 'add API key here.'
GLOB_HOSTNAME= "https://dpnc-indico.unige.ch/indico"

def contrib2twiki(cdict):
	ret = "  * **%s** - %s"%(cdict['title'],cdict['speaker'])
	if 'slides' in cdict:
		ret+=" [[%s|(slides)]]"%cdict['slides']
	return ret

def IS_OK(ret,msg):
	return {'OK':ret,'Message':msg}

def toTimeStamp(timeJson):
	y,m,d = [int(k) for k in str(timeJson['date']).split("-")]
	H,M,S = [int(k) for k in str(timeJson['time']).split(":")]
	dt = datetime.datetime(y,m,d,H,M,S)
	return time.mktime(dt.timetuple())

def nextMeeting(timeJson):
	''' returns true if next meeting is in future, else false '''
	timeNow = time.mktime(datetime.datetime.now().timetuple())
	timeStamp = toTimeStamp(timeJson)
	if timeStamp >= timeNow:
		return True
	return False

class IndicoObject(object):
	PATH= None
	ID = None
	API_KEY = GLOB_API_KEY
	PARAMS = {}
	URL = None
	JSON = None
	def __buildIndicoRequest__(self):
		items = self.PARAMS.items()
		items.append(('ak',self.API_KEY))
		items = sorted(items, key=lambda x: x[0].lower())
		path = '%s/%s.json'%(self.PATH,self.ID)
		self.URL = '%s?%s' % (path, urllib.urlencode(items))
		return self.URL
	
	def __init__(self,**kwargs):
		self.__dict__.update(kwargs)
		self.__setDefaults__()
		self.__buildIndicoRequest__()
	
	def __setDefaults__(self):
		self.PARAMS['limit']='123'
		self.PARAMS['pretty']='yes'
		self.PARAMS['onlypub']='no'
	
	def setObjectId(self,EVENT_ID):
		self.ID=EVENT_ID
	
	def validateJSON(self):
		if self.JSON is None:							return IS_OK(False,'JSON query empty, maybe something went wrong')
		if not self.JSON['complete']:			return IS_OK(False,'JSON query not complete')
		if not len(self.JSON['results']): return IS_OK(False,'JSON query seemingly okay, but results are empty')
		return IS_OK(True,"Everything is Fine")
	
	def submitQuery(self):
		context = ssl._create_unverified_context()
		try:
			f = urllib.urlopen(self.URL,context=context)
			raw_data = f.read()
			self.JSON = json.loads(raw_data)
		except IOError, io:
			return IS_OK(False,io)
		return True

class IndicoCategory(IndicoObject):
	PATH = "%s/export/categ"%GLOB_HOSTNAME
	PARAMS ={'detail':'events'}
	
	def getEvents(self,title):
		ret = []
		res = self.validateJSON()
		if not res['OK']:
			print 'error validating JSON, returning an empty list, error below'
			print	res['Message']
			return ret
		for ev in self.JSON['results']:
			if ev['title'] == title:
				ret.append(ev)
		return ret

class IndicoEvent(IndicoObject):
	PATH = "%s/export/event"%GLOB_HOSTNAME
	PARAMS = {'detail':'subcontributions'}
	
	def getContributions(self,with_material=True):
		''' returns the contributions as list of dictionaries '''
		ret = []
		res = self.validateJSON()
		if not res['OK']:
			print 'error validating JSON, returning an empty list, error below'
			print	res['Message']
			return ret
		contributions = self.JSON['results'][0]['contributions']
		#print 'ID: %i found %i contributions'%(self.ID,len(contributions))
		for contrib in contributions:
			contribId = contrib['id']
			for c in contrib['subContributions']:
				subID = c['id']
				#print "processing item %i"%i
				#print c
				r = {'title':c['title']}
				#r['timestamp'] = toTimeStamp(c['startDate'])
				if len(c['speakers']):
					r['speaker']=c['speakers'][0]['fullName']
					if len(c['speakers'][0]['affiliation']):
						r['speaker']+=" (%s)"%c['speakers'][0]['affiliation']
				else: r['speaker']='no speaker'
				if with_material:
					r['slides']="%s/getFile.py/access?subContId=%s&contribId=%s&resId=0&materialId=slides&confId=%s"%(GLOB_HOSTNAME,subID,contribId,self.ID)
					#mat = c['material']
					#if not len(mat):
					#		#print 'found no material associated with contribution %s'%r['title']
					#	continue
					#if not len(mat[0]['resources']):
					#		print 'found material but no resources for %s'%r['title']
					#	continue
					#r['slides']=mat[0]['resources'][0]['url']
				ret.append(r)
			#print r
		#print ret[-1]
		return ret #sorted(ret, key = lambda user: user['timestamp'])
	
	def getMinutes(self):
		ret = None
		res = self.validateJSON()
		if not res['OK']:
			print 'error validating JSON, returning an empty list, error below'
			print	res['Message']
			return ret
		material = self.JSON['results'][-1]['material']
		if len(material):
			for m in material:
				if m['id']=='minutes': ret = m['resources'][-1]['url']
		return ret


if __name__ == '__main__':
	from optparse import OptionParser
	parser = OptionParser()
	usage = "Usage: %prog [options]"
	description = "fetch Indico content from HOST"
	parser.set_usage(usage)
	parser.set_description(description)
	parser.add_option("--title",dest='title',default='DAMPE-EU Data Analysis Meetings',help="title to be used in twiki")
	parser.add_option("--meeting_title",dest='mtitle',default="DAMPE data analysis ",help="title of event in Indico")
	(opts, arguments) = parser.parse_args()
	doc_header = "===== DAMPE %s =====\n**Do not edit this page manually, as it is created by a bot**\n"%opts.title
	my_cat = IndicoCategory(ID=48)
	my_cat.submitQuery()
	events = reversed(my_cat.getEvents(title=opts.mtitle))
	print doc_header
	for i,ev in enumerate(events):
		startDate = ev['startDate']
		h = "**[[%s|%s]]**"%(ev['url'].replace("http","https")," ".join([startDate[key] for key in ['date','time','tz']]))
		if i == 0 and nextMeeting(startDate): h+= " **(next meeting)**"
		h+="\n"
		print h
		my_event = IndicoEvent(ID=int(ev['id']))
		my_event.submitQuery()
		contribs = my_event.getContributions()
		for c in contribs:
			print contrib2twiki(c)
		minutes = my_event.getMinutes()
		if minutes: print "   * [[%s|Minutes]]"%minutes
	print "\nLast Update: %s"%time.ctime()


