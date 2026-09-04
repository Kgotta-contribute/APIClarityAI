from pymongo import MongoClient

from app.config.config import settings

from datetime import datetime

from typing import Optional, List

import logging

 

logger = logging.getLogger(__name__)

 

class DatabaseService:

    def __init__(self):

        try:

            self.client = MongoClient(settings.mongo_uri)

            self.db = self.client[settings.mongodb_db_name]

            self.job_collection = self.db[settings.mongodb_job_collection]

        except Exception as e:

            print(f"Error connecting to MongoDB: {e}")

            logger.error(f"Error connecting to MongoDB: {str(e)}", exc_info=True)

            raise

   

    def create_job(self, job_data: dict) -> str:

        result = self.job_collection.insert_one(job_data)

        return str(result.inserted_id)

   

    def get_job_by_id(self, job_id: str) -> Optional[dict]:

        return self.job_collection.find_one({"jobID": job_id})

   

    def update_job_all_uploaded(self, job_id: str) -> bool:

        result = self.job_collection.update_one(

            {"jobID": job_id},

            {

                "$set": {

                    "status": "Uploaded",

                    "timeDetails.uploadedAt": datetime.utcnow()

                }

            }

        )

        return result.modified_count > 0

   

    def get_file_from_job(self, job_id: str, file_id: str) -> Optional[dict]:

        job = self.job_collection.find_one(

            {"jobID": job_id, "files.fileID": file_id},

            {"files.$": 1}

        )

        if job and "files" in job and len(job["files"]) > 0:

            return job["files"][0]

        return None

   

    def update_file_in_job(self, job_id: str, file_id: str, update_data: dict) -> bool:

        try:

            set_fields = {f"files.$.{key}": value for key, value in update_data.items()}

            result = self.job_collection.update_one(

            {"jobID": job_id, "files.fileID": file_id},

            {"$set": set_fields}

    )

            return result.modified_count > 0

        except Exception as e:

            print(f"Error updating file in job: {e}")

            logger.error(f"Error updating file in job - JobID: {job_id}, FileID: {file_id}, Error: {str(e)}", exc_info=True)

            return False

 

   

    def update_job_status(self, job_id: str, status: str) -> bool:

        update_fields = {"status": status}

        if status == "Uploaded":

            update_fields["timeDetails.uploadedAt"] = datetime.utcnow()

        result = self.job_collection.update_one(

            {"jobID": job_id},

            {"$set": update_fields}

        )

        return result.modified_count > 0

   

    def get_all_jobs(self, business_group = None, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None) -> List[dict]:

        """

        Get all jobs with optional filters.

       

        Args:

            business_group: Can be:

                - None: Return all documents (admin access)

                - str: Single business group to filter by

                - List[str]: Multiple business groups to filter by (uses $in)

            from_date: Filter jobs received on or after this date

            to_date: Filter jobs received on or before this date

       

        Returns:

            List of job documents sorted by receivedAt descending

        """

        query = {}

       

        if business_group is not None:

            if isinstance(business_group, list):

                # Multiple groups - use $in operator

                query["userDetails.businessGroup"] = {"$in": business_group}

            else:

                # Single group - direct match

                query["userDetails.businessGroup"] = business_group

       

        if from_date or to_date:

            date_query = {}

            if from_date:

                date_query["$gte"] = from_date

            if to_date:

                date_query["$lte"] = to_date

            query["timeDetails.receivedAt"] = date_query

       

        jobs = self.job_collection.find(query).sort("timeDetails.receivedAt", -1)

        return list(jobs)

   

    def count_jobs(self, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None) -> int:

        """

        Count total number of jobs in the collection with optional date filtering.

       

        Args:

            from_date: Filter jobs received on or after this date

            to_date: Filter jobs received on or before this date

       

        Returns:

            Total count of jobs matching the criteria

        """

        query = {}

       

        if from_date or to_date:

            date_query = {}

            if from_date:

                date_query["$gte"] = from_date

            if to_date:

                date_query["$lte"] = to_date

            query["timeDetails.receivedAt"] = date_query

       

        return self.job_collection.count_documents(query)

   

    def close(self):

        self.client.close()

 

db_service = DatabaseService()




if __name__ == "__main__":

    db_service.create_job({"jobID": "test", "status": "Created"})

    #print(db_service.get_job_by_id("test"))

    #db_service.update_job_all_uploaded("test")

    #print(db_service.get_job_by_id("test"))

    #db_service.close()