import urllib, urllib2, cookielib, json, re, xml.etree, os

class SurfRequest(urllib2.Request):
    """A request sent to a SpringSurf-based server. Adds support for additional method types in addition to GET and POST."""

    def __init__(self, url, data=None, headers={},
                 origin_req_host=None, unverifiable=False, method=None):
        urllib2.Request.__init__(self, url, data, headers, origin_req_host, unverifiable)
        self.http_method = method
    
    def get_method(self):
        if self.http_method is not None:
            return self.http_method
        else:
            return urllib2.Request.get_method(self)
    
    def set_method(self, method):
        self.http_method = method

class SurfRequestError(urllib2.HTTPError):
    """Error class for Surf Requests"""
    def __init__(self, method, url, code, msg, hdrs, fp):
        urllib2.HTTPError.__init__(self, url, code, msg, hdrs, fp)
        self.method = method
        self.respJSON = None
        self.description = ""
        self.exception = ""
        self.callstack = ""
        self.server = ""
        self.time = ""
        
        if ('Content-Type' in hdrs):
            self.respType = hdrs['Content-Type']
            try:
                self.respData = fp.read()
            except IOError, e:
                self.respData = ''
                pass
            if self.respType.startswith('application/json'):
                self.respJSON = json.loads(self.respData)
                self.description = self.respJSON['message']
                self.exception = self.respJSON['exception']
                self.callstack = self.respJSON['callstack']
                self.server = self.respJSON['server']
                self.time = self.respJSON['time']
    
    def __str__(self):
        if self.respJSON is not None:
            return 'Spring Surf Error %s (%s): "%s"' % (self.code, self.msg, self.description)
        else:
            return 'Spring Surf Error %s (%s)\n\n%s' % (self.code, self.msg, self.respData)

class ShareClient:
    """Access Alfresco Share progamatically via its RESTful API"""

    def __init__(self, url="http://localhost:8080/share", debug=0):
        """Initialise the client"""
        from MultipartPostHandler import MultipartPostHandler
        cj = cookielib.CookieJar()
        headers = [('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'), ('Accept-Charset', 'ISO-8859-1,utf-8;q=0.7,*;q=0.7'), ('Accept-Language', 'en-gb,en;q=0.5'), ('User-Agent', 'Mozilla/5.0 (X11; U; Linux i686; en-GB; rv:1.9.2.12) Gecko/20101027 Ubuntu/10.04 (lucid) Firefox/3.6.12')]
        # Regular opener
        opener = urllib2.build_opener(urllib2.HTTPHandler(debuglevel=debug), urllib2.HTTPCookieProcessor(cj))
        opener.addheaders = headers
        # Multipart opener
        #m_opener = urllib2.build_opener(MultipartPostHandler, urllib2.HTTPHandler(debuglevel=debug), urllib2.HTTPCookieProcessor(cj))
        m_opener = urllib2.build_opener(MultipartPostHandler, urllib2.HTTPCookieProcessor(cj))
        m_opener.addheaders = headers
        self.url = url
        self.opener = opener
        self.m_opener = m_opener
        self.debug = debug

    def doRequest(self, method, path, data=None, dataType=None):
        """Perform a general HTTP request against Share"""
        req = SurfRequest(url="%s/%s" % (self.url, path), data=data, method=method)
        if dataType is not None:
            req.add_header('Content-Type', dataType)
        try:
            return self.opener.open(req)
        except urllib2.HTTPError, e:
            raise SurfRequestError(method, e.url, e.code, e.msg, e.hdrs, e.fp)

    def doGet(self, path):
        """Perform a HTTP GET request against Share"""
        return self.doRequest("GET", path)

    def doPost(self, path, data="", dataType='application/x-www-form-urlencoded', method="POST"):
        """Perform a HTTP POST request against Share"""
        return self.doRequest(method, path, data, dataType)

    def doJSONGet(self, path):
        """Perform a HTTP GET request against Share and parse the output JSON data"""
        return json.loads(self.doGet(path).read())

    def doJSONPost(self, path, data="", method="POST"):
        """Perform a HTTP POST request against Share and parse the output JSON data"""
        jsonData = self.doPost(path, data, 'application/json; charset=UTF-8', method).read()
        if self.debug == 1:
            print jsonData
        return json.loads(jsonData)
    
    def doMultipartUpload(self, path, params):
        """Perform a multipart form upload against Share"""
        try:
            return self.m_opener.open("%s/%s" % (self.url, path), params)
        except urllib2.HTTPError, e:
            raise SurfRequestError("POST", e.url, e.code, e.msg, e.hdrs, e.fp)

    # Session functions

    def doLogin(self, username, password):
        """Log in to Share via the login servlet"""
        successurl = '/share/page/site-index'
        failureurl = '/share/page/type/login?error=true'
        resp = self.doPost('page/dologin', urllib.urlencode({'username': username, 'password': password, 'success': successurl, 'failure': failureurl}))
        if (resp.geturl() == '%s/page/user/%s/dashboard' % (self.url, username)):
            return { 'success': True }
        else:
            return { 'success': False }

    def doLogout(self):
        """Log the current user out of Share using the logout servlet"""
        resp = self.doGet('page/dologout')
    def updateDashboardConfig(self, configData):
        """Update a Share dashboard configuration"""
        result = {}
        result['dashboard-results'] = self.doJSONPost('service/components/dashboard/customise-dashboard', json.dumps(configData))
        result['dashlet-results'] = {}
        for dashlet in configData['dashlets']:
            if 'config' in dashlet:
                dashletId = 'page.%s.%s' % (dashlet['regionId'], configData['dashboardPage'].replace('/', '~'))
                print 'Setting config for dashlet %s' % (dashletId)
                result['dashlet-results'][dashletId] = self.setDashletConfig(dashletId, dashlet['config'])
        return result
    
    def setDashletConfig(self, dashletId, configData):
        """Update the configuration of a specific dashlet
        
        dashletId is something like "page.component-3-2.site~PartnerES~dashboard" or "page.component-3-2.user~wabson~dashboard"
        configData is a dictionary object defining the values to update
        """
        return self.doJSONPost('service/modules/dashlet/config/%s' % (dashletId), json.dumps(configData))
    
    # User functions
    
    def setProfileImage(self, username, imgpath):
        """Upload and set a profile image for a Share user"""
        uparams = { 'filedata' : file(imgpath, 'rb'), 'siteid':'', 'containerid':'', 'destination':'', 'username':username, 'updateNodeRef':'', 'uploadDirectory':'', 'overwrite':'false', 'thumbnails':'', 'successCallback':'', 'successScope':'', 'failureCallback':'', 'failureScope':'', 'contentType':'cm:content', 'majorVersion':'false', 'description':'' }
        fr = self.doMultipartUpload("proxy/alfresco/slingshot/profile/uploadavatar", uparams)
        udata = json.loads(fr.read())
        if udata['status']['code'] == 200:
            nodeRef = udata['nodeRef']
            return self.doJSONPost('service/components/profile/userprofile', '{"template_x002e_user-profile_x002e_user-profile-photoref":"%s"}' % (nodeRef))
        else:
            raise Exception("Could not upload file (got status code %s)" % (udata['status']['code']))

    def updateUserDetails(self, user):
        """Update the profile information for the current Share user"""
        jsonData = re.sub('\\"([-\\w]+)\\"\\:', '"template_x002e_user-profile_x002e_user-profile-input-\\1":', json.dumps(user))
        # Could also use POST /alfresco/service/slingshot/profile/userprofile
        return self.doJSONPost('service/components/profile/userprofile', jsonData)

    def updateUserDashboardConfig(self, user):
        """Update the a dashboard configuration for the current Share user"""
        return self.updateDashboardConfig(user['dashboardConfig'])
    
    # Site functions
    
    def getSiteInfo(self, siteId, getMetaData=False, getMemberships=False, getPages=False, getDashboardConfig=False):
        """Get information about a site"""
        siteData = self.doJSONGet('proxy/alfresco/api/sites/%s' % (siteId))
        if getMetaData:
            siteNodeRef = '/'.join(siteData['node'].split('/')[5:]).replace('/', '://', 1)
            siteData['metadata'] = self.doJSONGet('proxy/alfresco/api/metadata?nodeRef=%s' % (siteNodeRef))
        if getMemberships:
            siteData['memberships'] = self.doJSONGet('proxy/alfresco/api/sites/%s/memberships' % (siteId))
        # Since there is no JSON API to GET the site dashboard configuration, we need to query the AVM
        # sitestore directly on the repository tier. As the queries are proxied through the web tier, 
        # this should still work even if the repository is running on a different server to Share.
        if getPages:
            dashboardResp = self.doGet('proxy/alfresco/remotestore/get/s/sitestore/alfresco/site-data/pages/site/%s/dashboard.xml' % (siteId))
            from xml.etree.ElementTree import XML
            dashboardTree = XML(dashboardResp.read())
            sitePages = json.loads(dashboardTree.findtext('properties/sitePages', '[]'))
            siteData['sitePages'] = sitePages
        if getDashboardConfig:
            siteData['dashboardConfig'] = self.getDashboardConfig('site', siteId)
        return siteData
    
    def getDashboardConfig(self, dashboardType, dashboardId):
        """
        Get information on a site or user dashboard
        
        dashboardType is either 'site' or 'user'
        dashboardId is the site or user ID
        """
        try:
            dashboardResp = self.doGet('proxy/alfresco/remotestore/get/s/sitestore/alfresco/site-data/pages/%s/%s/dashboard.xml' % (dashboardType, dashboardId))
            from xml.etree.ElementTree import XML
            dashboardTree = XML(dashboardResp.read())
            templateInstance = dashboardTree.findtext('template-instance')
            dashlets = []
            # Iterate through dashboard components
            for i in [ 1, 2, 3 ]:
                for j in [ 1, 2, 3, 4 ]:
                    dashlet = { }
                    try:
                        #print 'proxy/alfresco/remotestore/get/s/sitestore/alfresco/site-data/components/page.component-%s-%s.%s~%s~dashboard.xml' % (i, j, dashboardType, dashboardId)
                        dashletResp = self.doGet('proxy/alfresco/remotestore/get/s/sitestore/alfresco/site-data/components/page.component-%s-%s.%s~%s~dashboard.xml' % (i, j, dashboardType, dashboardId))
                        dashletTree = XML(dashletResp.read())
                        dashlet['url'] = dashletTree.findtext('url')
                        dashlet['regionId'] = dashletTree.findtext('region-id')
                        
                        p = dashletTree.find('properties')
                        if p is not None:
                            props = p.getchildren()
                            if props:
                                dprops = {}
                                for p in props:
                                    dprops[p.tag] = str(p.text)
                                dashlet['config'] = dprops
                        
                        dashlets.append(dashlet)
                    except SurfRequestError, e:
                        if e.code == 404:
                            pass
                        else:
                            raise e
            dashboardConfig = { 'dashboardPage': '%s/%s/dashboard' % (dashboardType, dashboardId), 'templateId': templateInstance, 'dashlets': dashlets }
        except SurfRequestError, e:
            if e.code == 404:
                dashboardConfig = None
            else:
                raise e
        return dashboardConfig
    
    def createSite(self, siteData):
        """Create a Share site"""
        return self.doJSONPost('service/modules/create-site', json.dumps(siteData))
    
    def createRmSite(self, siteData):
        self.doGet('service/utils/create-rmsite?shortname=%s' % (siteData['shortName']))
        self.updateSite(siteData)
    
    def updateSite(self, siteData):
        """Update a Share site"""
        return self.doJSONPost('proxy/alfresco/api/sites/%s' % (siteData['shortName']), json.dumps(siteData), method="PUT")
    
    def setSitePages(self, pageData):
        """Set the pages from xml.etree.ElementTree import ElementTreepresent in a site
        
        pageData should be a dict object with keys 'pages' and 'siteId'"""
        return self.doJSONPost('service/components/site/customise-pages', json.dumps(pageData))

    def updateSiteDashboardConfig(self, siteData):
        """Update the a dashboard configuration for a site"""
        return self.updateDashboardConfig(siteData['dashboardConfig'])

    def addSiteMember(self, siteName, memberData):
        """Add a site member"""
        # TODO Support group and person objects as well as authority, as per web script doc
        authorityName = memberData['authority']['fullName']
        return self.doJSONPost('proxy/alfresco/api/sites/%s/memberships/%s' % (str(siteName), str(authorityName)), json.dumps(memberData), method="PUT")

    def addSiteMembers(self, siteName, membersData, skipMissingMembers=False):
        """Add one or more site members"""
        results = []
        for m in membersData:
            try:
                results.append(self.addSiteMember(siteName, m))
            except SurfRequestError, e:
                if skipMissingMembers == True:
                    pass
                else:
                    raise e
        return results
    
    def deleteSite(self, site):
        """Remove a Share site
        
        site can be a string value containing the siteName identifier or a dictionary object"""
        if type(site) == str:
            siteData = { 'shortName': site }
        else:
            siteData = site
        # Site API does not remove web-tier components
        #return self.doJSONPost('proxy/alfresco/api/sites', json.dumps(siteData), method="DELETE")
        return self.doJSONPost('service/modules/delete-site', json.dumps(siteData))
    
    def importSiteContent(self, siteId, containerId, f):
        """Upload a content package into the site and extract it"""
        #print "import content"
        # Get the site metadata
        siteData = self.doJSONGet('proxy/alfresco/api/sites/%s' % (siteId))
        siteNodeRef = '/'.join(siteData['node'].split('/')[5:]).replace('/', '://', 1)
        treeData = self.doJSONGet('proxy/alfresco/slingshot/doclib/treenode/node/%s' % (siteNodeRef.replace('://', '/')))
        #print treeData
        # Locate the container item
        containerData = None
        tempContainerData = None
        tempContainerName = 'temp'
        for child in treeData['items']:
            if child['name'] == containerId:
                containerData = child
            if child['name'] == 'temp':
                tempContainerData = child
        if containerData is None:
            # Create container if it doesn't exist
            folderData = { 'alf_destination': siteNodeRef, 'prop_cm_name': containerId, 'prop_cm_title': containerId, 'prop_cm_description': '' }
            createData = self.doJSONPost('proxy/alfresco/api/type/cm_folder/formprocessor', json.dumps(folderData))
            containerData = { 'nodeRef': createData['persistedObject'], 'name' : containerId }
            # Add the tagscope aspect to the container - otherwise an error occurs when viewed by a site consumer
            self.doPost('proxy/alfresco/slingshot/doclib/action/aspects/node/%s' % (str(containerData['nodeRef']).replace('://', '/')), '{"added":["cm:tagscope"],"removed":[]}', 'application/json;charset=UTF-8')
            #print createData
            #raise Exception("Container '%s' does not exist" % (containerId))
        if tempContainerData is None:
            # Create upload container if it doesn't exist
            folderData = { 'alf_destination': siteNodeRef, 'prop_cm_name': tempContainerName, 'prop_cm_title': tempContainerName, 'prop_cm_description': '' }
            createData = self.doJSONPost('proxy/alfresco/api/type/cm_folder/formprocessor', json.dumps(folderData))
            tempContainerData = { 'nodeRef': createData['persistedObject'], 'name' : tempContainerName }
        # First apply a ruleset to the temp folder
        # This will perform the import automatically when we upload the ACP file
        rulesetDef = {
            'id': '',
            'action': {
                "actionDefinitionName":"composite-action",
                "conditions": [
                    {
                        "conditionDefinitionName":"compare-property-value",
                        "parameterValues": {
                            "operation":"ENDS",
                            "value":".acp",
                            "property":"cm:name"
                        }
                    }
                ],
                "actions": [
                    {
                        "actionDefinitionName":"import",
                        "parameterValues": {
                            "destination":containerData['nodeRef']
                        }
                    }
                ]
            },
            "title":"Import ACP file",
            "description":"",
            "disabled": False,
            "applyToChildren": False,
            "executeAsynchronously": False,
            "ruleType":["inbound"]
        }
        rulesData = self.doJSONPost('proxy/alfresco/api/node/%s/ruleset/rules' % (tempContainerData['nodeRef'].replace('://', '/')), json.dumps(rulesetDef))
        # Now upload the file
        uparams = { 'filedata' : f, 'siteid':siteId, 'containerid':tempContainerName, 'destination':'', 'username':'', 'updateNodeRef':'', 'uploadDirectory':'/', 'overwrite':'false', 'thumbnails':'', 'successCallback':'', 'successScope':'', 'failureCallback':'', 'failureScope':'', 'contentType':'cm:content', 'majorVersion':'false', 'description':'' }
        fr = self.doMultipartUpload("proxy/alfresco/api/upload", uparams)
        udata = json.loads(fr.read())
        if udata['status']['code'] == 200:
            nodeRef = udata['nodeRef']
            #jsonResp = self.doJSONPost('proxy/alfresco/slingshot/doclib/action/import/node/%s' % (nodeRef.replace('://', '/')))
            #TODO Investigate how this can be done without using the custom 'import' web script
            # Remove the rule definition
            self.doJSONPost('proxy/alfresco/api/node/%s/ruleset/rules/%s' % (containerData['nodeRef'].replace('://', '/'), rulesData['data']['id']), method="DELETE")
            #importParams = { 'actionDefinitionName': 'import', 'actionedUponNode': nodeRef, 'parameterValues' : [ 'destination': '' ], 'executeAsync': false }
            #jsonResp = self.doJSONPost('/api/actionQueue?async=false/%s' % (nodeRef.replace('://', '/')), json.dumps(importParams))
            # Delete the ACP file
            self.doJSONPost('proxy/alfresco/slingshot/doclib/action/file/node/%s' % (nodeRef.replace('://', '/')), method="DELETE")
        else:
            raise Exception("Could not upload file (got status code %s)" % (udata['status']['code']))

    # Admin functions
    
    def getAllUsers(self, getFullDetails=False, getDashboardConfig=False, getPreferences=False):
        """Fetch information on all the person objects in the repository"""
        pdata = self.doJSONGet('proxy/alfresco/api/people')
        if getFullDetails or getDashboardConfig or getPreferences:
            for p in pdata['people']:
                if getFullDetails:
                    p.update(self.doJSONGet('proxy/alfresco/api/people/%s' % (p['userName'])))
                if getDashboardConfig:
                    dc = self.getDashboardConfig('user', p['userName'])
                    if dc != None:
                        p['dashboardConfig'] = dc
                if getPreferences:
                    p['preferences'] = self.doJSONGet('proxy/alfresco/api/people/%s/preferences' % (p['userName']))
        return pdata
        
    def createUser(self, user):
        """Create a person object in the repository"""
        if not ('password' in user):
            print "Warning: using default password for user %s" % (user['userName'])
            user['password'] = user['userName']
        return self.doJSONPost('proxy/alfresco/api/people', json.dumps(user))

    def createUsers(self, users, skip_users=[]):
        """Create several person objects in the repository"""
        for u in users:
            if not (u['userName'] in skip_users):
                print "Creating user '%s'" % (u['userName'])
                try:
                    self.createUser(u)
                except urllib2.HTTPError, e:
                    if e.code == 409:
                        print "User '%s' already exists, skipping" % (u['userName'])
                    else:
                        print e
    
    def setUserPreferences(self, username, prefs):
        return self.doJSONPost('proxy/alfresco/api/people/%s/preferences' % (username), json.dumps(prefs))
    
    def deleteUser(self, user):
        """Delete an existing user from Share"""
        return self.doJSONPost("%s/%s" % ('proxy/alfresco/api/people', user), data="", method="DELETE")

    def deleteUsers(self, users):
        """Delete several person objects from the repository"""
        for u in users:
            print "Deleting user '%s'" % (u['userName'])
            try:
                self.deleteUser(u['userName'])
            except SurfRequestError, e:
                if e.code == 404:
                    print "User '%s' did not exist, skipping" % (u['userName'])
                else:
                    raise e

