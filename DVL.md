# Setup for DVL 1.5 (Infectious Diseases)

## Network:
Host-only

## Getting more ports:
Once VM is running type in username and password

username: root 

password: toor or root

Next type startx and click next

Once open go to terminal and type in following commands to see which ports are open:

netstat -tuln | grep LISTEN
or just netstat -tuln 

### Ports already available
This should show the followign open ports (can confirm by running nmap IP on kali):
- Port 631, service ipp
- Port 3306, service mysql
- port 6000, service X11

#### Changing system to allow writing
The first step is to check if system is read-only or not, use the following command to check:

mount | grep ' / '

If output is ro then you need to run the following command to write:

mount -o remount,rw /

#### Starting HTTP port
To open http port, type in command:

/usr/local/apache/bin/httpd
or 
/usr/local/apache/bin/httpd -k start


#### Starting SSH port
run: /usr/sbin/sshd

otherwise run: 
ssh-keygen -t rsa1 -f /etc/ssh/ssh_host_key -N ""
ssh-keygen -t rsa  -f /etc/ssh/ssh_host_rsa_key -N ""
ssh-keygen -t dsa  -f /etc/ssh/ssh_host_dsa_key -N ""
/usr/sbin/sshd

#### Starting DNS port
run: /usr/sbin/named

#### Available ports
- Port 22, service ssh
- Port 53, service domain
- Port 80, service http
- Port 631, service ipp
- Port 3306, service mysql
- port 6000, service X11


# Setup for DVL 1.0

## Network:
Host-only or Bridged Adapter

## Getting root access:
In the terminal run: sudo su
check you are root with: whoami

Once open go to terminal and type in following commands to see which ports are open 

netstat -tuln | grep LISTEN
or just netstat -tuln 

### Ports already available
This should show the followign open ports (can confirm by running nmap IP on kali):
- Port 68

#### Changing system to allow writing
The first step is to check if system is read-only or not, use the following command to check:

mount | grep ' / '

If output is ro then you need to run the following command to write:

mount -o remount,rw /

#### Starting SSH port
run: /etc/init.d/ssh start

#### Starting any port available
To get list of services run: ls /etc/init.d
Then to start any service from that list run command: /etc/init.d/SERVICE_NAME start

#### Available ports
- Port 22, service ssh
- Port 60
