## Distributed, coordinated, scheduled snapshots for GlusterFS

This document describes an approach to get distributed, coordinated and scheduled snapshots for [GlusterFS][gluster-site] volumes.

[TOC]
### Introduction
Scheduled snapshots are a required feature for any enterprise storage product. [Volume level snapshots][volume-snaps] were introduced in GlusterFS-3.6.

Currently, GlusterFS volume snapshots can be easily scheduled by setting up [cron][cron-wiki] jobs on one of the nodes in the GlusterFS trusted storage pool. This is has a single point failure (SPOF), as scheduled jobs can be missed if the node running the cron jobs dies.

We can avoid the SPOF by distributing the cron jobs to all nodes of the trusted storage pool. This could lead to problems with multiple nodes attempting to perform the same snapshot due to lack of coordination between the nodes.

The rest of the document describes how we can solve the above problems to arrive at distributed, coordinated, scheduled snapshots.

### Detailed description
The solution to the above problems involves the usage of a *shared volume*, a *helper script* and depends on features provided by *[cronie][cronie]*

- Shared volume
  This is a normal GlusterFS volume, that will be used to share the schedule configuration and will help in the coordination of the jobs.
- Helper script
  The script will perform the actual snapshot commands, instead of cron. The script will contain the logic to perform coordinated snapshots.
- cronie
  *cronie* is the default cron daemon shipped with RHEL. *cronie* provides users with a set of directories, `/etc/cron.{hourly,daily,weekly,monthly}`. When any executable file is dropped into one of these directories, *cronie* will run them on a schedule based on the name of directory. We will make use of this feature of *cronie*.

#### Initial setup
The helper script needs to be dropped into the `/etc/cron.{hourly,daily,weekly,monthly}` directories on all nodes in the trusted storage pool. The script could be made available as a package, which would make this step easier.

The administrator will then need to create a volume to be used as the shared volume, and make sure that the shared volume is mounted on all nodes in the trusted storage pool. It could be mounted at `/var/run/gluster/shared-volume/` (`$SV`) as the standard location. It is preferable to have the *shared volume* be a replicate volume to avoid SPOF.

#### Shared volume structure
The *shared volume* will contain a directory structure along the lines of the cron directories, ie. `/schedule-{hourly,daily,weekly,monthly}`.
To schedule a snapshot, the administrator needs to just create a directory entry with the volumes name in the specific directory. For *eg.*, to schedule snapshots of volume A every hour, the administrator just needs to do `touch $SV/schedule-hourly/A`. To remove a schedule just remove the entry.

#### Helper script
> NOTE: It is assumed that all nodes in the have their times synced using NTP or any other mechanism. This is a requirement for any distributed system.

The helper script then performs the scheduled snapshots using the following algorithm to coordinate.

```Pseudocode
start_time = get current time
entries = read directory entries from specific schedule directory on $SV
foreach entry in $entries, do
	try POSIX locking the $entry
	if lock is obtained, then
		mod_time = Get modification time of $entry
		if $mod_time < $start_time, then
			Take snapshot of $entry.name (Volume name)
			if snapshot failed, then
				log the failure
			Update modification time of $entry to current time
		unlock the $entry
	
```

The helper script will be run on each node on a scheduled basis (hourly, daily, etc.) by the cron daemons on each node.

The script gets the list of volumes, for which need to have snapshots taken, by reading the directory entries of the specific directory on the *shared volume*.

The coordination with other scripts running on other nodes, is handled by the use of POSIX locks. All the instances of the script will attempt to lock the entry, and one which gets the lock will take the snapshot.

To prevent redoing a done task, the script will make use of the *mtime* attribute of the entry. At the beginning execution, the script would have saved its *start time*. Once the script obtains the lock on an entry, before taking the snapshot, it compares the *mtime* of the entry with the *start time*. The snapshot will only be taken if the *mtime* is smaller than *start time*. Once the snapshot command completes, the script will update the *mtime* of the entry to the current time before unlocking.

If a snapshot command fails, the script will log the failure (in syslog) and continue with its operation. It will not attempt to retry the failed snapshot in the current schedule, but will attempt it again in the next schedules. It is left to the administrator to monitor the logs and decide what to do after a failure.

#### Drawback
Following this approach has a drawback in that custom schedules are not possible. The schedules are fixed to hourly, daily, weekly and monthly periods.

An administrator wanting custom schedules would need to create custom crontab entries and manage its distribution to all nodes in the trusted pool. The administrator will need to take care of coordination between the nodes. An algorithm similar to the helper script could be used. The helper script itself could be generalized to allow use in such a case.


[gluster-site]: https://gluster.org
[cron-wiki]: https://en.wikipedia.org/wiki/Cron
[volume-snaps]: http://www.gluster.org/community/documentation/index.php/Features/Gluster_Volume_Snapshot
[cronie]: https://fedorahosted.org/cronie/

