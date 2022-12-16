import inspect,os,json,shlex,tempfile,csv,ipywidgets as ipw,subprocess
from IPython.display import FileLink

#XnatUtils
class XnUt:
    
    ipw_style={'description_width':'initial'}    
    lay_wid60={'width':'60pt'}
    lay_wid100={'width':'100pt'}
    lay_wid150={'width':'150pt'}
    lay_wid200={'width':'200pt'}
    lay_wid250={'width':'250pt'}
    lay_wid400={'width':'400pt'}
    
    def __init__(self):
        pass
    
    def inspect_object(obj,inspect_istype):    
        #e.g. inspect.isclass
        for m in inspect.getmembers(obj,inspect_istype):
            print(m[0])
        
    def execute(cmd):
        popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True)
        for stdout_line in iter(popen.stdout.readline, ""):
            yield stdout_line 
        popen.stdout.close()
        return_code = popen.wait()
        if return_code:
            raise subprocess.CalledProcessError(return_code, cmd)
            
    def show_file_link(out,file):
        out.outputs=();  f=FileLink(file)
        with out:
            display(f)
            
    def list_dict2csv(scans, file):
        '''Write a list of dicts to a csv file.'''
        with open(file, 'w') as output_file:
            dict_writer = csv.DictWriter(output_file, scans[0].keys())
            dict_writer.writeheader()
            dict_writer.writerows(scans)

    def csv2list_dict(file):
        '''Read a csv file into a list of dictionaries.'''
        with open(file,'r') as inf:
            reader = csv.DictReader(inf)
            scans=[{k: str(v) for k,v in row.items()} 
                      for row in csv.DictReader(inf,skipinitialspace=True)]
        return scans    
                   
            
class ServerParams:
    '''
    Container parameters received from XNAT
    '''
    def __init__(self,server=None, user=None, password=None, project=None,subject=None,experiment=None):
        self.server,self.user,self.password,self.project,self.subject,self.experiment= \
            server,user,password,project,subject,experiment
        self.jsession=''
        self.connected=False

    def __str__(self):
        return "server:{}, user: {}, project: {}, subject: {}, experiment: {}, connected: {}".\
            format(self.server,self.user,self.project,self.subject,self.experiment,self.connected)
        
    def connect(self):
        cmd="curl -k -u "+ self.user+":"+self.password+ \
            " "+self.server+"/data/JSESSION"
        self.jsession=os.popen(cmd).read()
        self.connected=(len(self.jsession)==32)
        return self.connected
    
    def serialize(self,fil,dic,is_read):
        try:
            if is_read:
                dic={}
                if os.path.exists(fil):
                    with open(fil,'r') as fp:
                        dic=json.load(fp)
                    self.server,self.user,self.project,self.subject=dic['server'],dic['user'],dic['project'],dic['subject']
            else:
                with open(fil,'w') as fp:
                    dic['server'],dic['user'],dic['project'],dic['subject']=self.server,self.user,self.project,self.subject
                    json.dump(dic,fp)
        except:
            print(sys.exc_info())
        
        
class XnatIterator:
    def __init__(self,sp):
        self.sp=sp
        self._subjects=[]
        self._experiments=[]
        self._scans=[]
        self._verbosity=0
            
    def _curl_cmd_prefix(self):
        return "curl  -k --cookie JSESSIONID=" + self.sp.jsession
    
    def _curl_cmd_path(self,path):
        return shlex.quote(self.sp.server+"/data/archive/projects/"+self.sp.project+path)
    
    def _curl_cmd(self,path):
        cmd=self._curl_cmd_prefix()+' '+self._curl_cmd_path(path)
        if self._verbosity>0:
            print(cmd)
        out=os.popen(cmd).read()
        return(out)
    
    def _curl_dcmdump_cmd(self,path):
        cmd=self._curl_cmd_prefix()+' '+shlex.quote(self.sp.server+"/data/services/dicomdump?src=/archive/projects/"+self.sp.project+path)
        if self._verbosity>0: print(cmd)
        out=os.popen(cmd).read()
        return(out)
    
    def curl_download_single_file(self,path,dest):
        cmd=self._curl_cmd_prefix()+' -o '+dest+' '+ self.sp.server + path
        if self._verbosity>0: print (cmd)
        return os.popen(cmd).read()
        
    def curl_download_scan(self,subject,experiment,scan,work_dir,dest_dir):
        path=self._curl_cmd_path(
            '/subjects/{}/experiments/{}/scans/{}/files?format=zip'.format(subject,experiment,scan))                
        fil=tempfile.NamedTemporaryFile(mode='w+b', suffix='.zip', prefix='scan_', dir=work_dir)
        cmd='{} -o {} {}'.format(self._curl_cmd_prefix(),fil.name,path)
        if self._verbosity>0: print(cmd)
        os.system(cmd)
        os.system('unzip '+fil.name+' -d '+work_dir)
        os.system('mkdir -p '+dest_dir)
        os.system('mv ' + work_dir + '/'+experiment+'/scans/'+scan+'-*/resources/DICOM/files/* '+dest_dir)
        os.system('rm -rf '+ work_dir + '/' + experiment)
        
    def set_project(self,pr):
        self.sp.project=pr
    
    def list_subjects(self):
        tq=self._curl_cmd('/subjects?format=json')
        try: 
            df=json.loads(tq)
        except:
            return []

        subjs=sorted(df['ResultSet']['Result'], key=lambda k:k['label'])        
        self._subjects=[f['label'] for f in subjs]
        return self._subjects
    
    def scan_file_loader(self,scans,tdir,lock):
        for s in scans:
            #print(s)
            files=self.list_scan_files(s['subject'],s['experiment'],s['ID'])
            if len(files)>0:
                t=tdir+'/'+s['subject']+'_'+s['experiment']+'_'+s['ID']
                self.curl_download_single_file(files[0],t+'.dcm')
                os.system("dcmj2pnm +G +Wn +on "+t+".dcm "+ t + ".png")
                os.system( "rm -f " + t + ".dcm" )
                lock.acquire()
                s['png'] = t+".png"
                lock.release()
            else:
                s['png']='N/A'
    
    def list_experiments(self,subject,return_dict=False):
        tq=self._curl_cmd('/subjects/'+subject+"/experiments?xsiType=xnat:imageSessionData&format=json") 
        try: 
            df=json.loads(tq)
        except: 
            print ('error listing experiments!')
            return []
        exps=sorted(df['ResultSet']['Result'], key=lambda k:k['date'])
        self._experiments=[f['label'] for f in exps]
        if not return_dict:
            return self._experiments
        expd={}
        for e in exps: expd[e['label']]=e
        return expd
    
    def list_scans(self,subject,experiment, listDcmFiles=False, include_dcm_tags=[], include_xnat_fields=[]):
        '''
        listDcmFiles: list all files that belong to this scan
        include_dcm_tags: get specified DICOM tags using the dicomdump service
        dcm tag format: "[group][element]", e.g. "0020000d"
        '''
        #print(1)
        columns="ID,frames,type,series_description"
        if len(include_xnat_fields)>0:
            columns+=","+",".join(include_xnat_fields)
            
        sf=self._curl_cmd('/subjects/'+ subject +'/experiments/' \
            +experiment + "/scans?columns="+columns)
        try:
            df=json.loads(sf)
        except:
            print('cannot load from {}!'.format(sf))
            return []
        self._scans=sorted(df['ResultSet']['Result'], key=lambda k:k['xnat_imagescandata_id'])
        for s in self._scans:
            s['subject']=subject
            s['experiment']=experiment
        
        if listDcmFiles:
            for s in self._scans:
                files=self.list_scan_files(subject,experiment,s['ID'])
                s['files']=files
                
        if len(include_dcm_tags) > 0:
            tag_query=""
            for tag in include_dcm_tags:
                tag_query+="&field="+tag
            for s in self._scans:
                sf=self._curl_dcmdump_cmd('/subjects/'+ subject +'/experiments/' \
                    +experiment + '/scans/'+s['ID']+tag_query)
                try: 
                    ds=json.loads(sf)      
                    tag_vals=XnatIterator.get_dcm_tag_values(ds,include_dcm_tags)
                except: 
                    print('cannot load JSON!')
                    return []
                for tag,val in zip(include_dcm_tags,tag_vals):
                    s[tag]=val                
        return self._scans
    
    def get_dcm_tag_values(ds,tag_list):
        res=ds['ResultSet']['Result']
        tags=[ t['tag1'] for t in res ]
        vals=[ t['value'] for t in res ]
        out_vals=[]
        for t in tag_list:
            s='('+t[:4]+','+t[4:]+')'
            ind=tags.index(s)
            out=vals[ind] if ind >= 0 else ''
            out_vals+=[out]
        return out_vals
                
    
    def get_dcm_files_for_scans(self,subject,experiment,scans):
        for s in scans:
            files=self.list_scan_files(subject,experiment,s['ID'])
            s['files']=files
        
    def list_scan_files(self,subject,experiment,scan):
        sf=self._curl_cmd('/subjects/'+ subject +'/experiments/' \
            +experiment + '/scans/'+scan+'/resources/DICOM/files')        
        try: df=json.loads(sf)
        except: return []
        df=json.loads(sf)
        
        lst=sorted(df['ResultSet']['Result'], key=lambda k:k['Name'])
        return [ f['URI'] for f in lst ]        
    """
    list all scans in project, filtered by subject prefix. 
    Display progres in output textarea.
    Save output in speficified json file.
    """
    def list_scans_all(self,subjects,subject_prefix,output,json_out_file=None):
        scans,ns,nsubj=[],0,len(subjects)
        subind=0
        for su in subjects:
            subind+=1
            if not su.lower().startswith(subject_prefix.lower()): continue
            experiments=self.list_experiments(su)
            for e in experiments:
                if output: output.value='Subject {} ({}/{}), total scans: {}'.format(su,subind,nsubj,ns)
                sscans=self.list_scans(su,e)
                for s in sscans:
                    scans.append(s)
                    ns+=1
        if json_out_file is not None:
            with open(json_out_file, 'w') as fp:
                json.dump(scans, fp)
        return scans
    
    """
    list all scans contained in the list of experiments. 
    Display progres in output textarea.
    Save output in speficified json file.
    """
    def list_scans_in_experiments(self,subjects,experiments,output,json_out_file=None, include_dcm_tags=[],\
                                 include_xnat_fields=[]):
        scans,ns,nexp=[],0,len(experiments)
        subind,ns=0,0
        if len(subjects) != nexp: 
            #print('list_scans_in_experiments: number of subjects must be equal to number of experiments!')
            raise ValueError('list_scans_in_experiments: number of subjects must be equal to number of experiments!')
        
        for sub,e,ind in zip(subjects,experiments,range(nexp)):
            if output: output.value='{} ({}/{}), scans: {}'.format(e,ind,nexp,ns)
            #print('self.list_scans({},{})'.format(sub,e))
            sscans=self.list_scans(sub,e,include_dcm_tags=include_dcm_tags,\
                                   include_xnat_fields=include_xnat_fields)
            for s in sscans:
                scans.append(s)
                ns+=1
                
        if json_out_file is not None:
            with open(json_out_file, 'w') as fp:
                json.dump(scans, fp)
        return scans
    
    
    
class GUIPage():
    def __init__(self, parent, title, page_num, max_page, btn1_label=None, btn2_label=None, frontdesk=None,plumbing=None):
        style={'description_width':'initial'}
        self._parent_box,self.frontdesk,self.plumbing=parent,frontdesk,plumbing
        self._title, self._btn1_label, self._btn2_label, self._page_num, self._max_page=title, \
            btn1_label, btn2_label, page_num, max_page
        self._html_title=ipw.HTML(value='<h4>'+title+'</h4>')
#        (value=title,style={'description_width':'initial','font-size':'small'},layout={'width':'800px'})
        self.main_box=ipw.VBox([])
        self._lb_dis, self._rb_dis=False,False
        if page_num==0: self._lb_dis=True
        if page_num==max_page-1: self._rb_dis=True
        if btn1_label is None: btn1_label='Prev'
        if btn2_label is None: btn2_label='Next'
            
        self._prev_btn=ipw.Button(description=btn1_label,tooltip=str(page_num),disabled=self._lb_dis,layout={'width':'200px'})
        self._next_btn=ipw.Button(description=btn2_label,tooltip=str(page_num),disabled=self._rb_dis,layout={'width':'200px'})
        
        self._btm_indent_img=ipw.Image(width=1,height=50,layout={'width':'1px','height':'100px'})    
        self._nav_box=ipw.HBox([self._prev_btn,self._next_btn])
        self._btm_box=ipw.VBox([self._btm_indent_img,self._nav_box])
        
        if not frontdesk is None:
            self.main_box.children=[frontdesk.main_box]
            
    def set_title(self,str):
        self._html_title.value='<h4>'+str+'</h4>'
        
    def show(self):
        self._parent_box.children=[self._html_title,self.main_box,self._btm_box]
        if not self.frontdesk is None:
            self.frontdesk.refresh()

class GUIBook():
    def __init__(self, pages):
        self._num_pages=len(pages)
        self.main_box=ipw.VBox()
        self.pages=[]
        for i in range(self._num_pages):
            p=pages[i]
            fd=p['frontdesk']
            
            pg=GUIPage(self.main_box,p['title'],i,self._num_pages,
                       btn1_label=p['prev_label'],btn2_label=p['next_label'],
                       frontdesk=fd,plumbing=p['plumbing'])
            if fd is not None: fd.set_nav_page(pg)
                
            self.pages+=[pg]
            pg._prev_btn.on_click(self._prev_click)
            pg._next_btn.on_click(self._next_click)
            
        if self._num_pages>0:            
            self._cur_page=0
            self.pages[0].show()
        display(self.main_box)
        
    def _prev_click(self,b):
        if self._cur_page==0: return
        self._cur_page-=1
        self.pages[self._cur_page].show()
    
    def _next_click(self,b):
        if self._cur_page==self._num_pages-1: return
        self._cur_page+=1
        self.pages[self._cur_page].show()         
    
class FrontDesk:
    def set_nav_page(self,pg):
        self._nav_page=pg
        
    def enable_nav_next(self,enable):
        self._nav_page._next_btn.disabled=not enable
        
    def enable_nav_prev(self,enable):
        self._nav_page._prev_btn.disabled=not enable    
        
class XNATLogin(FrontDesk):
    def __init__(self,serialize_file):
        self._connected=False
        self._serialize_file=serialize_file
        st={'description_width':'initial'}
        layout=ipw.Layout(margin='0 100pt 0 0')
        layout1=ipw.Layout(justify_content='center')
        
        self.sp=ServerParams()
        self.sp.serialize(serialize_file,{},True)
        
        self.text1=ipw.Text(value=self.sp.server, description='XNAT server:', 
                            layout={'width':'200pt'}, style=st, disabled=False)
#        self.text1=ipw.Text(value='https://cnda.wustl.edu', description='XNAT server:', 
#                            layout={'width':'200pt'}, style=st, disabled=False)

        self.text2=ipw.Text(value=self.sp.user,description='user:',
                                disabled=False, style=st, layout={'width':'120pt'})
        self.text3=ipw.Password(value='',description='password:',
                                disabled=False, style=st, layout={'width':'120pt'})
        self.lbl1=ipw.Label('status: not connected', layout={'width':'120pt'}, style=st) #layout={'width':'240px','justify-content':'center'}
        lbl2=ipw.Label('',layout={'width':'120pt'},style=st)
        self.btn1=ipw.Button(description="connect",style={},layout={'width':'200pt'})
        self.btn1.on_click(self.on_connect)
        vb1=ipw.HBox([self.text1,self.text2,self.text3])
        vb2=ipw.HBox([self.btn1,lbl2,self.lbl1])
        self.main_box=ipw.VBox([vb1,vb2])
        
        
    def refresh(self):
        self.enable_nav_next(False)
        
    def on_connect(self,b):
        #self._show_scanview(False)
        self.lbl1.value='status: connecting...'
        self.sp.server,self.sp.user,self.sp.password=self.text1.value,self.text2.value,self.text3.value
        
        if self.sp.connect():                    
            self.lbl1.value='status: connected'
            self.btn1.description='Reconnect'            
            self.connected=True
            self.enable_nav_next(True)
            self.sp.serialize(self._serialize_file,{},False)
        else:
            self.lbl1.value='status: connection failed'    
            #print(self.sp.jsession)
            self.enable_nav_next(False)

class SubjectSelector:
    def __init__(self,server_params,serialize_file,project_changed_callback=None, subject_changed_callback=None):
        #print('SubjectSelector.init')
        self._sp=server_params
        self._serialize_file=serialize_file
        self.prj_changed_callback=project_changed_callback
        self.sbj_changed_callback=subject_changed_callback
        
        style={'description_width':'initial'}
        self._drop_prj=ipw.Dropdown(description='project:',style=style,layout={'width':'200px'})
        self._drop_prj.observe(self._on_project_changed,names='value')        
        self._drop_sbj=ipw.Dropdown(description='subject:',style=style,layout={'width':'200px'})                       
        self._drop_sbj.observe(self._on_subject_changed,names='value')        
        self._lbl_status=ipw.Label(description='ready',style=style,layout={'width':'200px'})                                                
        self.main_box=ipw.HBox([self._drop_prj, self._drop_sbj, self._lbl_status])
        #print('SubjectSelector.init.before_project_list')
        #self._project_list()
        #print('SubjectSelector.init.after_project_list')
        self._prj_changed_first_time=True
        #display(self.main_box)
    
    def freeze(self,freeze):
        self._drop_prj.disabled=freeze
        self._drop_sbj.disabled=freeze        
    
    def _query_prefix(self):
        return "curl -k --cookie JSESSIONID=" + self._sp.jsession + " " + self._sp.server+"/data/archive/projects/"
    
    def _project_list(self):
        sl=self._lbl_status
        if not self._sp.connected: sl.value='not connected!'; return
        cmd=self._query_prefix()+'?format=json'
        sl.value='listing projects...'        
        df=json.loads(os.popen(cmd).read())
        projs=sorted(df['ResultSet']['Result'], key=lambda k:k['ID'])        
        self._projects=[f['ID'] for f in projs]
        
        self._drop_prj.options=self._projects
        
        
        #print('_project_list')
        #print('self._sp.project',self._sp.project)
        #print(self._sp)
        sl.value='ready'
        
    def _subject_list(self):
        if self._drop_prj.value is None: return        
        sl=self._lbl_status
        cmd=self._query_prefix()+self._drop_prj.value+'/subjects?format=json'
        sl.value='listing subjects...'
        df=json.loads(os.popen(cmd).read())
        subjs=sorted(df['ResultSet']['Result'], key=lambda k:k['label'])
        self._subjects=[f['label'] for f in subjs]
        if len(self._subjects) > 0:
            self._drop_sbj.options=self._subjects
            self._drop_sbj.value=self._subjects[0]
            #print(self._sp)
            self._lbl_status.value='found {} subject(s)'.format(len(self._subjects))      
        else:
            self._lbl_status.value='no subjects found'
        
    def _on_project_changed(self,b):
        #print('on_project_changed')
        #print('self._sp.project before changing',self._sp.project)
        if self._prj_changed_first_time:
            #print("self.sp.prject",self._sp.project,"options:",self._drop_prj.options)
            if self._sp.project in self._drop_prj.options:
                self._drop_prj.value=self._sp.project
            self._prj_changed_first_time=False    
              
        self._sp.project=self._drop_prj.value
        #print('self._sp.project after changing',self._sp.project)
        self._sp.serialize(self._serialize_file,{},False) 
        self._subject_list()
        if not self.prj_changed_callback is None: self.prj_changed_callback()
        
    def _on_subject_changed(self,b):
        self._sp.subject=self._drop_sbj.value
        if not self.sbj_changed_callback is None: self.sbj_changed_callback()
            
    def refresh(self):
        self._project_list()
        
                
class ScanSelector:
    def __init__(self, server_params, annotation,exp_changed_callback=None,selection_callback=None,
                scan_types=[]):
        select_scan_type=True if len(scan_types)>0 else False
        self._sp,self._annot,self._exp_changed_callback=server_params,annotation,exp_changed_callback
        self._selection_callback,self._sel_scan_type,self._scan_types=selection_callback,select_scan_type,scan_types
        
        self._annot_html=ipw.HTML(value='<b>'+annotation+'</b>')
        style={'description_width':'initial'}
        
        self._drop_exp=ipw.Dropdown(description='study:',style=style,layout={'width':'250px'})
        self._drop_exp.observe(self._on_experiment_changed,names='value')
        self._lbl_status=ipw.Label(description='ready',style=style,layout={'width':'200px'})        
        self._topbox=ipw.VBox([self._annot_html,ipw.HBox([self._drop_exp,self._lbl_status])])
        
        self.main_box=ipw.VBox([self._topbox])
        self._xi=XnatIterator(self._sp)
        self._subject=None
        #display(self.main_box)
        
    def freeze(self, freeze):
        self._drop_exp.disabled=freeze
        for i in range(2,len(self.main_box.children)):
            self.main_box.children[i].children[0].disabled=freeze
    
    def _on_experiment_changed(self,b):
        #print('_on_experiment_changed')
        self._experiment=self._drop_exp.value
        #self.main_box.children=[ self._annot_html, self._drop_exp ]
        self.show_scans()
        if not self._exp_changed_callback is None: self._exp_changed_callback()
        
    def update_subject(self):
        #print('update_subject')                
        self._list_experiments()
        #self.main_box.children=[ self._annot_html, self._drop_exp ]
        if len(self._experiments)>0:
            self._drop_exp.value=self._experiments[0]
    
    def _query_prefix(self):
        return "curl -k --cookie JSESSIONID=" + self._sp.jsession + " " + self._sp.server+\
            "/data/archive/projects/"+self._sp.project+"/subjects/"+self._sp.subject+\
            "/experiments/"
    
    def _list_experiments(self):
        #print('_list_experiments')
        sl=self._lbl_status
        cmd=self._query_prefix()+"?format=json"
        #print(cmd)
        sl.value='listing experiments...'
        df=json.loads(os.popen(cmd).read())
        exps=sorted(df['ResultSet']['Result'], key=lambda k:k['date'])    
        self._experiments=[f['label'] for f in exps]
        self._exp_dicts={}
        for e in exps: self._exp_dicts[e['label']]=e
        
        self._drop_exp.options=self._experiments        
        self._drop_exp.value=self._experiments[0]
        sl.value='found {} experiment(s)'.format(len(self._experiments))
        
    def show_scans(self):
        if self._sp.subject is None or self._experiment is None: return        
        scans=self._xi.list_scans(self._sp.subject,self._experiment)
        self._scans=scans
        style={'description_width':'initial'}
        rows=[self._topbox]
        header=[
            ipw.Label(value='Use',style=style,layout={'width':'60px'}),
            ipw.Label(value='ID',style=style,layout={'width':'60px'}),
            ipw.Label(value='Description',style=style,layout={'width':'250px'}),
            ipw.Label(value='Frames',style=style,layout={'width':'60px'})
        ]
        if self._sel_scan_type: header+=[ipw.Label(value='Type',style=style,layout={'width':'100px'})]
        rows+=[ipw.HBox(header)]
        
        for s in scans:
            ch=ipw.Checkbox(value=False,description='',style=style,layout={'width':'60px'})
            if self._selection_callback is not None:
                ch.observe(self._selection_callback)
            row=[
                ch,
                ipw.Label(value=s['ID'],style=style,layout={'width':'60px'}),
                ipw.Label(value=s['series_description'],style=style,layout={'width':'250px'}),
                ipw.Label(value=s['frames'],style=style,layout={'width':'60px'})
            ]
            if self._sel_scan_type: 
                sel=ipw.Dropdown(description='',style=style,layout={'width':'100px'})
                sel.options,sel.value=self._scan_types,None
                sel.observe(self.on_scan_type_selection_changed,names='value')
                sel.value=None
                row+=[sel]
            rows+=[ipw.HBox(row)]
            
        self.main_box.children=rows
    
    def on_scan_type_selection_changed(self,b):
        #print(b['owner'])
        for i in range(2,len(self.main_box.children)):
            row=self.main_box.children[i].children
            if row[4]==b['owner']: 
                if row[0].value: row[0].value=False
                row[0].value=True
        
        
    def get_selected_scans(self):
        sel_scans=[]
        exp=self._exp_dicts[self._experiment]
        date=exp['date'] if 'date' in exp.keys() else None 
        for i in range(2,len(self.main_box.children)):
            row=self.main_box.children[i].children
            if row[0].value:
                s=self._scans[i-2]; s['experiment']=self._experiment
                if self._sel_scan_type: s['type']=row[4].value
                s['date']=date
                sel_scans+=[s]
        return sel_scans
    
class ProcessWithTextProgress:
    def __init__(self,btn_descr, btn_on_click):
        style={'description_width':'initial'}
        self.lbl_status=ipw.Label(description='status: ready',style=style,layout={'width':'200px'})
        self._btn_run=ipw.Button(description=btn_descr,disabled=True,layout={'width':'150px'})
        self._btn_run.on_click(btn_on_click)
        self.out=ipw.Output(layout={'width':'600px','height':'300px','overflow_y':'auto'})
        self.main_box=ipw.VBox([
            ipw.HBox([self._btn_run,self.lbl_status]),
            self.out
        ])
        self.clear()       
        
    def clear(self):
        self.status('status: ready')
        self.out.value=''
            
    def status(self,s):
        self.lbl_status.value=s        
            